#!/usr/bin/env python3
"""Unchanged native banks; measure both axes of a multiple-choice probe."""
import argparse
import hashlib
import json
from pathlib import Path

import torch

from checkpoint_runtime import inspect_checkpoint, load_model


QUERY = """Which pair is correct?
A. oolong; Lima
B. oolong; Oslo
C. coffee; Lima
D. coffee; Oslo
Answer only A, B, C, or D."""
ARMS = [("none", []), ("drink_only", [0]), ("city_only", [1]), ("both", [0, 1])]


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def choice_metrics(logits, token_ids):
    labels = logits[token_ids].double()
    conditional = labels.softmax(-1)
    log_probs = labels - logits.double().logsumexp(-1)
    return dict(
        logits=dict(zip("ABCD", labels.tolist())),
        probabilities_full_vocab=dict(zip("ABCD", log_probs.exp().tolist())),
        probabilities_given_ABCD=dict(zip("ABCD", conditional.tolist())),
        label_probability_mass=float(log_probs.exp().sum()),
        label_log_probability_mass=float(log_probs.logsumexp(-1)),
        drink_axis_probability_given_ABCD=float(conditional[0] + conditional[1]),
        city_axis_probability_given_ABCD=float(conditional[0] + conditional[2]),
        drink_axis_log_odds=float(labels[[0, 1]].logsumexp(-1) - labels[[2, 3]].logsumexp(-1)),
        city_axis_log_odds=float(labels[[0, 2]].logsumexp(-1) - labels[[1, 3]].logsumexp(-1)),
        A_logit_margins={key: float(labels[0] - labels[i]) for i, key in enumerate("ABCD") if i},
        top_choice="ABCD"[int(labels.argmax())])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["source", "train", "records", "out"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    r = inspect_checkpoint(args.source, args.train)
    sources = json.loads(args.records.read_text())
    assert set(sources) == {"d1", "d2"}
    selected = []
    for role, answer in [("d1", "oolong"), ("d2", "Lima")]:
        source = sources[role]
        matches = [(i, m) for i, m in enumerate(r.metadata["memories"])
                   if m["content"] == source["memory"]["content"]]
        assert len(matches) == 1
        index, memory = matches[0]
        assert memory["answer"] == answer
        selected.append((source["memory"]["id"], index))
    assert [mid for mid, _ in selected] == [5, 6]
    assert sources["d1"]["store"] == sources["d2"]["store"]
    assert sources["d1"]["memory"]["scope"] == sources["d2"]["memory"]["scope"]
    prompt = r.ref.prompt_ids(r.tokenizer, dict(query=QUERY))
    decoded = r.tokenizer.decode(prompt)
    assert all(s["memory"]["content"] not in decoded for s in sources.values())
    encoded = [r.tokenizer.encode(label, add_special_tokens=False) for label in "ABCD"]
    assert all(len(tokens) == 1 for tokens in encoded), "labels require sequence scoring"
    label_ids = [tokens[0] for tokens in encoded]
    assert len(set(label_ids)) == 4
    assert [r.tokenizer.decode([token]) for token in label_ids] == list("ABCD")
    write(args.out / "sources.json", sources)
    write(args.out / "protocol.json", dict(query=QUERY, arms=ARMS,
        label_token_ids=dict(zip("ABCD", label_ids)),
        measurement="Raw first-generated-token logits; full-vocabulary probabilities and probabilities conditional on A/B/C/D.",
        memory_text_injected=False, answer_values_present_in_choices=True,
        adaptation="none", native_path="unchanged original learned attention"))
    write(args.out / "provenance.json", dict(checkpoint=r.compatibility,
        records_sha256=r.ref.digest(args.records),
        implementation={name: r.ref.digest(Path(__file__).with_name(name))
                        for name in ["run_choice.py", "checkpoint_runtime.py"]}, training_steps=0))
    load_model(r)
    layer = r.adapter.layer.requires_grad_(False).eval()
    r.model.requires_grad_(False).eval()
    original_forward = layer.forward.__func__
    p = next(layer.parameters())
    initial = {name: value.detach().cpu().clone() for name, value in layer.state_dict().items()}
    vectors = [r.saved["values"]["values"][index].detach().to(p.device, p.dtype) for _, index in selected]
    original_vectors = [value.cpu().clone() for value in vectors]
    eos = r.model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    results = {}
    with torch.inference_mode():
        for name, positions in ARMS:
            assert layer.forward.__func__ is original_forward
            ids = [selected[i][0] for i in positions]
            bank = layer.prepare(ids, torch.stack([vectors[i] for i in positions]), 1) if positions else None
            calls = []
            handle = layer.query.register_forward_pre_hook(lambda module, inputs: calls.append(1))
            try:
                tensor = torch.tensor([prompt], device=r.input_device)
                with r.adapter.using(bank):
                    result = r.model.generate(input_ids=tensor, attention_mask=torch.ones_like(tensor),
                        max_new_tokens=32, do_sample=False, eos_token_id=eos,
                        pad_token_id=r.tokenizer.pad_token_id or eos[0], use_cache=True,
                        return_dict_in_generate=True, output_scores=True, output_logits=True)
            finally:
                handle.remove()
            tokens = result.sequences[0, len(prompt):].tolist()
            answer = r.tokenizer.decode(tokens, skip_special_tokens=True)
            terminated = bool(tokens and tokens[-1] in eos)
            assert bool(calls) == bool(positions)
            raw = result.logits[0][0].detach().float().cpu()
            metrics = choice_metrics(raw, label_ids)
            torch.save(raw, args.out / (name + "-first-token-logits.pt"))
            row = dict(arm=name, bank_ids=ids, answer=answer, terminated=terminated,
                valid_choice=terminated and answer.strip() in "ABCD" and len(answer.strip()) == 1,
                generated_ids=tokens, query=QUERY, token_ids=prompt, native_prompt=decoded,
                prompt_sha256=hashlib.sha256(json.dumps(prompt).encode()).hexdigest(),
                prompt_tokens=len(prompt), injected_memory_text_tokens=0,
                answer_values_present_in_choices=True, learned_query_calls=len(calls),
                first_token_metrics=metrics,
                top_first_token_id=int(raw.argmax()),
                top_first_token_text=r.tokenizer.decode([int(raw.argmax())]))
            results[name] = row
            write(args.out / (name + ".json"), row)
            print(json.dumps({k: v for k, v in row.items() if k not in ["token_ids", "native_prompt"]}), flush=True)
        parameters_unchanged = all(torch.equal(initial[name], value.cpu()) for name, value in layer.state_dict().items())
        vectors_unchanged = all(torch.equal(old, value.cpu()) for old, value in zip(original_vectors, vectors))
        assert parameters_unchanged and vectors_unchanged
        assert len({row["prompt_sha256"] for row in results.values()}) == 1
        metrics = {name: row["first_token_metrics"] for name, row in results.items()}
        shifts = {name: {axis: m[axis + "_axis_log_odds"] - metrics["none"][axis + "_axis_log_odds"]
                         for axis in ["drink", "city"]} for name, m in metrics.items() if name != "none"}
        write(args.out / "summary.json", dict(status="complete", query=QUERY,
            results={name: {k: row[k] for k in ["bank_ids", "answer", "valid_choice", "first_token_metrics"]}
                     for name, row in results.items()}, axis_log_odds_shifts_vs_none=shifts,
            prompt_parity=True, injected_memory_text_tokens=0, answer_values_present_in_choices=True,
            parameters_unchanged=parameters_unchanged, vectors_unchanged=vectors_unchanged,
            native_path_unchanged=True, training_steps=0, trainable_parameters=0,
            limits="One fixed option order; no-memory choice priors and absolute label probability mass must accompany conditional scores."))
    r.adapter.close()
    for hook in r.hooks:
        hook.remove()


if __name__ == "__main__":
    main()
