#!/usr/bin/env python3
"""Three identical-prompt arms; singleton success gates composition claims."""
import argparse
import hashlib
import json
from pathlib import Path

import torch

from checkpoint_runtime import inspect_checkpoint, load_model


QUERY = "Return exactly: <drink>; <city>. Use unknown for any value you do not know."
ARMS = [
    ("drink_only", [0], "oolong; unknown"),
    ("city_only", [1], "unknown; Lima"),
    ("both", [0, 1], "oolong; Lima"),
]


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


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
    assert "oolong" not in decoded.casefold() and "lima" not in decoded.casefold()
    write(args.out / "sources.json", sources)
    write(args.out / "protocol.json", dict(query=QUERY, arms=ARMS,
        rule="Composition is adjudicated only if both singleton arms pass.",
        adaptation="none", native_path="unchanged original learned attention"))
    write(args.out / "provenance.json", dict(checkpoint=r.compatibility,
        records_sha256=r.ref.digest(args.records),
        implementation={name: r.ref.digest(Path(__file__).with_name(name))
                        for name in ["run_composition.py", "checkpoint_runtime.py"]}, training_steps=0))
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
        for name, positions, expected in ARMS:
            assert layer.forward.__func__ is original_forward
            ids = [selected[i][0] for i in positions]
            bank = layer.prepare(ids, torch.stack([vectors[i] for i in positions]), 1)
            calls = []
            handle = layer.query.register_forward_pre_hook(lambda module, inputs: calls.append(1))
            try:
                tensor = torch.tensor([prompt], device=r.input_device)
                with r.adapter.using(bank):
                    result = r.model.generate(input_ids=tensor, attention_mask=torch.ones_like(tensor),
                        max_new_tokens=32, do_sample=False, eos_token_id=eos,
                        pad_token_id=r.tokenizer.pad_token_id or eos[0], use_cache=True,
                        return_dict_in_generate=True, output_scores=True)
            finally:
                handle.remove()
            tokens = result.sequences[0, len(prompt):].tolist()
            answer = r.tokenizer.decode(tokens, skip_special_tokens=True)
            terminated = bool(tokens and tokens[-1] in eos)
            assert calls, "original native selector was not used"
            row = dict(arm=name, bank_ids=ids, expected=expected, answer=answer,
                terminated=terminated, passed=terminated and r.ref.value_match(answer, expected),
                exact_match=terminated and answer.strip() == expected,
                generated_ids=tokens, query=QUERY, token_ids=prompt, native_prompt=decoded,
                prompt_sha256=hashlib.sha256(json.dumps(prompt).encode()).hexdigest(),
                prompt_tokens=len(prompt), added_memory_tokens=0, learned_query_calls=len(calls))
            results[name] = row
            write(args.out / (name + ".json"), row)
            print(json.dumps({k: v for k, v in row.items() if k not in ["token_ids", "native_prompt"]}), flush=True)
        parameters_unchanged = all(torch.equal(initial[name], value.cpu()) for name, value in layer.state_dict().items())
        vectors_unchanged = all(torch.equal(old, value.cpu()) for old, value in zip(original_vectors, vectors))
        assert parameters_unchanged and vectors_unchanged
        assert len({row["prompt_sha256"] for row in results.values()}) == 1
        prerequisites = results["drink_only"]["passed"] and results["city_only"]["passed"]
        conclusion = ("composition_success" if results["both"]["passed"] else "composition_failure") if prerequisites else "prompt_latent_generalization_issue"
        write(args.out / "summary.json", dict(status="complete", query=QUERY,
            results={name: {k: row[k] for k in ["bank_ids", "expected", "answer", "terminated", "passed", "exact_match"]}
                     for name, row in results.items()},
            singleton_prerequisites_passed=prerequisites, composition_adjudicated=prerequisites,
            conclusion=conclusion, prompt_parity=True, zero_memory_tokens=True,
            parameters_unchanged=parameters_unchanged, vectors_unchanged=vectors_unchanged,
            native_path_unchanged=True, training_steps=0, trainable_parameters=0,
            limits="One fixed prompt and two existing projections. Failed singleton prerequisites preclude a composition conclusion."))
    r.adapter.close()
    for hook in r.hooks:
        hook.remove()


if __name__ == "__main__":
    main()
