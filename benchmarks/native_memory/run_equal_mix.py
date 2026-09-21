#!/usr/bin/env python3
"""One intervention: replace competitive attention with constant 1/2, 1/2."""
import argparse
import hashlib
import json
from pathlib import Path
from types import MethodType

import torch

from checkpoint_runtime import inspect_checkpoint, load_model


def equal_forward(layer, hidden, bank):
    if bank is None or not bank.ids:
        return hidden
    if len(bank.ids) != 2:
        raise ValueError("this intervention requires exactly two memories")
    base_dtype = hidden.dtype
    hidden = hidden.to(layer.query.weight.dtype)
    # Same aggregation matmul, output, gate and residual boundary as the
    # original forward. Only query/key/softmax selection is bypassed.
    weights = hidden.new_full((*hidden.shape[:-1], 2), 0.5)
    residual = layer.output(weights @ bank.values)
    return (hidden + layer.gate(hidden).sigmoid() * residual).to(base_dtype)


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["source", "train", "records", "prior", "out"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    r = inspect_checkpoint(args.source, args.train)
    sources = json.loads(args.records.read_text())
    prior = json.loads(args.prior.read_text())
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
    ids = [mid for mid, _ in selected]
    assert ids == prior["bank_ids"] == [5, 6]
    assert sources["d1"]["store"] == sources["d2"]["store"]
    assert sources["d1"]["memory"]["scope"] == sources["d2"]["memory"]["scope"]
    prompt = r.ref.prompt_ids(r.tokenizer, dict(query=prior["query"]))
    assert prompt == prior["token_ids"]
    decoded = r.tokenizer.decode(prompt)
    for source in sources.values():
        assert source["memory"]["content"] not in decoded
    assert "oolong" not in decoded.casefold() and "lima" not in decoded.casefold()
    write(args.out / "sources.json", sources)
    write(args.out / "provenance.json", dict(checkpoint=r.compatibility,
        records_sha256=r.ref.digest(args.records), prior_sha256=r.ref.digest(args.prior),
        implementation={name: r.ref.digest(Path(__file__).with_name(name))
                        for name in ["run_equal_mix.py", "checkpoint_runtime.py"]},
        bank_ids=ids, training_steps=0, intervention="constant weights [0.5, 0.5] at all prefill/decode positions"))
    load_model(r)
    layer = r.adapter.layer.requires_grad_(False).eval()
    r.model.requires_grad_(False).eval()
    original = layer.forward
    p = next(layer.parameters())
    initial = {name: value.detach().cpu().clone() for name, value in layer.state_dict().items()}
    values = torch.stack([r.saved["values"]["values"][index] for _, index in selected]).to(p.device, p.dtype)
    eos = r.model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    results = {}
    with torch.inference_mode():
        bank = layer.prepare(ids, values, 1)
        for mode in ["learned", "equal"]:
            telemetry, selector_calls = [], []
            layer.forward = original if mode == "learned" else MethodType(equal_forward, layer)
            def count_selector(module, inputs):
                selector_calls.append(type(module).__name__)
                if mode == "equal":
                    raise AssertionError("competitive selector executed during equal mixing")
            selector_handles = [module.register_forward_pre_hook(count_selector) for module in [layer.norm, layer.query]]
            def inspect(module, inputs, output):
                hidden, current = inputs
                h = hidden[:, -1:]
                telemetry.append(dict(phase="prefill" if hidden.shape[1] > 1 else "decode",
                    weights=[0.5, 0.5] if mode == "equal" else None,
                    gate=float(layer.gate(h.to(p.dtype)).sigmoid().mean()),
                    residual_over_hidden=float((output[:, -1:].float() - h.float()).norm() / h.float().norm().clamp_min(1e-12))))
            handle = layer.register_forward_hook(inspect)
            try:
                tensor = torch.tensor([prompt], device=r.input_device)
                with r.adapter.using(bank):
                    result = r.model.generate(input_ids=tensor, attention_mask=torch.ones_like(tensor),
                        max_new_tokens=32, do_sample=False, eos_token_id=eos,
                        pad_token_id=r.tokenizer.pad_token_id or eos[0], use_cache=True,
                        return_dict_in_generate=True, output_scores=True)
            finally:
                handle.remove()
                for handle in selector_handles:
                    handle.remove()
            tokens = result.sequences[0, len(prompt):].tolist()
            answer = r.tokenizer.decode(tokens, skip_special_tokens=True)
            terminated = bool(tokens and tokens[-1] in eos)
            row = dict(mode=mode, answer=answer, terminated=terminated, generated_ids=tokens,
                expected="oolong; Lima", passed=terminated and r.ref.value_match(answer, "oolong; Lima"),
                exact_match=terminated and r.ref.normalized(answer) == r.ref.normalized("oolong; Lima"),
                query=prior["query"], token_ids=prompt, native_prompt=decoded,
                prompt_sha256=hashlib.sha256(json.dumps(prompt).encode()).hexdigest(),
                prompt_tokens=len(prompt), added_memory_tokens=0, bank_ids=ids,
                selector_module_calls=len(selector_calls), telemetry=telemetry)
            results[mode] = row
            write(args.out / (mode + ".json"), row)
            print(json.dumps({k: v for k, v in row.items() if k not in ["token_ids", "native_prompt", "telemetry"]}), flush=True)
        layer.forward = original
        unchanged = all(torch.equal(initial[name], value.cpu()) for name, value in layer.state_dict().items())
        assert unchanged
        assert results["equal"]["selector_module_calls"] == 0
        control_reproduced = results["learned"]["generated_ids"] == prior["generated_ids"]
        write(args.out / "summary.json", dict(status="complete", expected="oolong; Lima",
            learned_answer=results["learned"]["answer"], equal_answer=results["equal"]["answer"],
            equal_passed=results["equal"]["passed"], control_reproduced=control_reproduced,
            prompt_matches_previous=True, zero_memory_tokens=True, parameters_unchanged=unchanged,
            training_steps=0, trainable_parameters=0, selector_calls_equal=0,
            weights=[0.5, 0.5], bank_ids=ids,
            limits="One query, two fixed existing values; failure does not distinguish averaging loss from downstream interference."))
    r.adapter.close()
    for hook in r.hooks:
        hook.remove()


if __name__ == "__main__":
    main()
