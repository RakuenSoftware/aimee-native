#!/usr/bin/env python3
"""Establish trained direct-answer behavior before assessing native composition."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import torch

from checkpoint_runtime import inspect_checkpoint, load_model


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
    training = r.ref.read_fixture(r.fixtures, "train.json")
    selected = []
    for role, answer in [("d1", "oolong"), ("d2", "Lima")]:
        source = sources[role]
        matches = [(i, m) for i, m in enumerate(r.metadata["memories"])
                   if m["content"] == source["memory"]["content"]]
        assert len(matches) == 1
        index, memory = matches[0]
        assert memory["answer"] == answer
        # Use an exact query seen during training, selected before generation.
        examples = [row for row in training if row["memory_ids"] == [memory["memory_id"]]]
        example = sorted(examples, key=lambda row: row["id"])[0]
        selected.append(dict(id=source["memory"]["id"], index=index, memory=memory,
                             query=example["query"], training_example=example))
    assert [row["id"] for row in selected] == [5, 6]
    assert sources["d1"]["store"] == sources["d2"]["store"]
    assert sources["d1"]["memory"]["scope"] == sources["d2"]["memory"]["scope"]
    composition_query = (f"Give the preferred drink of {selected[0]['memory']['entity']}, "
                         f"then the home city of {selected[1]['memory']['entity']}. Separate with a semicolon.")
    queries = {"drink": selected[0]["query"], "city": selected[1]["query"], "composition": composition_query}
    # Fix all arms before model loading; do not adapt prompts to observed results.
    arms = [
        ("drink_single", "drink", [0], "native", "oolong"),
        ("city_single", "city", [1], "native", "Lima"),
        ("drink_shared", "drink", [0, 1], "native", "oolong"),
        ("city_shared", "city", [0, 1], "native", "Lima"),
        ("composition_none", "composition", [], "none", "oolong; Lima"),
        ("composition_text", "composition", [], "text", "oolong; Lima"),
        ("composition_native", "composition", [0, 1], "native", "oolong; Lima"),
    ]
    write(args.out / "sources.json", sources)
    write(args.out / "protocol.json", dict(queries=queries, arms=arms,
        singleton_training_examples=[s["training_example"] for s in selected],
        composition_template_training_example=next(row for row in training if len(row["memory_ids"]) == 2),
        composition_pair_seen_in_training=any(set(row["memory_ids"]) == {s["memory"]["memory_id"] for s in selected} for row in training),
        rule="Require singleton and shared-bank direct-answer checks plus a passing text-composition control before attributing failure to composition.",
        adaptation="none", native_path="unchanged original learned attention"))
    write(args.out / "provenance.json", dict(checkpoint=r.compatibility,
        records_sha256=r.ref.digest(args.records),
        implementation={name: r.ref.digest(Path(__file__).with_name(name))
                        for name in ["run_matched_probe.py", "checkpoint_runtime.py"]}, training_steps=0))
    load_model(r)
    layer = r.adapter.layer.requires_grad_(False).eval()
    r.model.requires_grad_(False).eval()
    original_forward = layer.forward.__func__
    p = next(layer.parameters())
    initial = {name: value.detach().cpu().clone() for name, value in layer.state_dict().items()}
    vectors = [r.saved["values"]["values"][s["index"]].detach().to(p.device, p.dtype) for s in selected]
    original_vectors = [value.cpu().clone() for value in vectors]
    eos = r.model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    results = {}
    with torch.inference_mode():
        for name, query_name, positions, mode, expected in arms:
            assert layer.forward.__func__ is original_forward
            ids = [selected[i]["id"] for i in positions]
            bank = layer.prepare(ids, torch.stack([vectors[i] for i in positions]), 1) if positions else None
            query = queries[query_name]
            plain = r.ref.prompt_ids(r.tokenizer, dict(query=query))
            prompt = r.ref.prompt_ids(r.tokenizer, dict(query=query),
                [sources[role]["memory"] for role in ["d1", "d2"]] if mode == "text" else None)
            decoded = r.tokenizer.decode(prompt)
            if mode != "text":
                assert prompt == plain
                assert "oolong" not in decoded.casefold() and "lima" not in decoded.casefold()
                assert all(s["memory"]["content"] not in decoded for s in sources.values())
            telemetry = []
            def observe_query(module, inputs, output):
                q = output[:, -1:]
                weights = ((q @ bank.keys.T) / math.sqrt(q.shape[-1])).float().softmax(-1)
                telemetry.append(dict(phase="prefill" if output.shape[1] > 1 else "decode",
                    memory_ids=ids, attention=weights.flatten().tolist()))
            handle = layer.query.register_forward_hook(observe_query)
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
            assert bool(telemetry) == bool(positions)
            row = dict(arm=name, mode=mode, bank_ids=ids, expected=expected, answer=answer,
                terminated=terminated, passed=terminated and r.ref.value_match(answer, expected),
                generated_ids=tokens, query=query, token_ids=prompt, native_prompt=decoded,
                prompt_sha256=hashlib.sha256(json.dumps(prompt).encode()).hexdigest(),
                prompt_tokens=len(prompt), added_memory_text_tokens=len(prompt)-len(plain),
                telemetry=telemetry)
            results[name] = row
            write(args.out / (name + ".json"), row)
            print(json.dumps({k: v for k, v in row.items() if k not in ["token_ids", "native_prompt", "telemetry"]}), flush=True)
        parameters_unchanged = all(torch.equal(initial[name], value.cpu()) for name, value in layer.state_dict().items())
        vectors_unchanged = all(torch.equal(old, value.cpu()) for old, value in zip(original_vectors, vectors))
        assert parameters_unchanged and vectors_unchanged
        assert all(results[a]["token_ids"] == results[b]["token_ids"] for a, b in [
            ("drink_single", "drink_shared"), ("city_single", "city_shared"), ("composition_none", "composition_native")])
        singles_pass = all(results[name]["passed"] for name in ["drink_single", "city_single"])
        shared_pass = all(results[name]["passed"] for name in ["drink_shared", "city_shared"])
        text_pass = results["composition_text"]["passed"]
        prerequisites = singles_pass and shared_pass and text_pass
        if not singles_pass:
            conclusion = "trained_singleton_behavior_not_reproduced"
        elif not shared_pass:
            conclusion = "shared_bank_single_fact_selection_failed_composition_not_isolated"
        elif not text_pass:
            conclusion = "text_composition_control_failed_composition_not_isolated"
        elif results["composition_native"]["passed"]:
            conclusion = "native_composition_success" if not results["composition_none"]["passed"] else "correct_but_no_memory_control_also_passed"
        else:
            conclusion = "native_composition_failure_for_this_pair_and_prompt"
        write(args.out / "summary.json", dict(status="complete", queries=queries,
            results={name: {k: row[k] for k in ["bank_ids", "expected", "answer", "terminated", "passed", "added_memory_text_tokens"]}
                     for name, row in results.items()},
            singleton_checks_passed=singles_pass, shared_bank_checks_passed=shared_pass,
            text_control_passed=text_pass, composition_adjudicated=prerequisites, conclusion=conclusion,
            matched_prompt_parity=True, parameters_unchanged=parameters_unchanged,
            vectors_unchanged=vectors_unchanged, native_path_unchanged=True,
            training_steps=0, trainable_parameters=0,
            limits="Fixed pair and prompts. Singles are exact training queries; the joint query uses a trained format with a new pair. No broad generalization claim."))
    r.adapter.close()
    for hook in r.hooks:
        hook.remove()


if __name__ == "__main__":
    main()
