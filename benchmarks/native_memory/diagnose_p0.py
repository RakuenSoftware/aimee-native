#!/usr/bin/env python3
"""Bounded post-hoc diagnostics; load the pilot's immutable implementation.

Not a Stage A acceptance run. Interventions and the source checkpoint are
recorded separately rather than relaxing its compatibility check.
"""
import argparse
from collections import defaultdict
import hashlib
import importlib
import json
import math
from pathlib import Path
import sys
import time

import torch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(args.source.resolve()))
    ref = importlib.import_module("run_p0")
    saved = torch.load(args.train / "adapter.pt", map_location="cpu", weights_only=True)
    identity = saved["identity"]
    recorded = json.loads((args.train / "arguments.json").read_text())
    for name, expected in identity["implementation_sha256"].items():
        if ref.digest(args.source / name) != expected:
            raise ValueError(f"original implementation mismatch: {name}")
    model_path = Path(identity["model"])
    for name, expected in identity["local_weight_sha256"].items():
        if ref.digest(model_path / name) != expected:
            raise ValueError(f"weight mismatch: {name}")
    config = ref.AutoConfig.from_pretrained(str(model_path), trust_remote_code=False)
    tokenizer = ref.AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=False)
    for field, value in [("config_sha256", config.to_json_string()),
                         ("tokenizer_sha256", tokenizer.backend_tokenizer.to_str()),
                         ("chat_template_sha256", str(tokenizer.chat_template))]:
        if hashlib.sha256(value.encode()).hexdigest() != identity[field]:
            raise ValueError(f"{field} mismatch")
    if str(torch.__version__) != identity["torch"] or ref.transformers.__version__ != identity["transformers"]:
        raise ValueError("library version mismatch")
    fixtures = Path(recorded["fixtures"])
    if json.loads((fixtures / "sha256.json").read_text()) != identity["fixtures"]:
        raise ValueError("fixture manifest mismatch")
    metadata = ref.read_fixture(fixtures, "memories.json")
    memories = {m["memory_id"]: m for m in metadata["memories"]}
    active = {mid for mid, m in memories.items() if m["active"]}
    cls = {"qwen3_5": ref.Qwen3_5ForConditionalGeneration, "qwen3_5_text": ref.Qwen3_5ForCausalLM}[config.model_type]
    model = cls.from_pretrained(str(model_path), dtype=getattr(torch, identity["dtype"]),
                               attn_implementation="eager", trust_remote_code=False).eval().requires_grad_(False)
    if identity["base_quantization"] == "int8_per_row_v1":
        ref.quantize_frozen_linears(model)
    elif identity["base_quantization"] != "none":
        raise ValueError("unknown quantization")
    placement = identity["placement"]
    hooks = ref.place(model, placement)
    adapter = ref.FrozenQwenEngram(model, identity["value_width"], identity["attention_width"], identity["after_block"])
    adapter.layer.load_state_dict(saved["layer"])
    table = ref.OracleValues(list(memories), identity["value_width"], metadata["scope"], metadata["generation"]).to(
        device=next(adapter.layer.parameters()).device, dtype=getattr(torch, identity["dtype"]))
    table.load_state_dict(saved["values"])
    eos = model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    manifest = dict(checkpoint_sha256=ref.digest(args.train / "adapter.pt"), identity=identity,
                    diagnostic_sha256=ref.digest(Path(__file__)),
                    selection="first two per category in each split; no outcome-based selection",
                    interventions=["original_k16", "oracle_only", "swapped_same_category", "none", "text_oracle"],
                    acceptance_run=False)
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    records = []
    with torch.no_grad(), (args.out / "diagnostics.jsonl").open("x") as log:
        for split in ["train", "heldout"]:
            counts = defaultdict(int)
            for example in ref.read_fixture(fixtures, split + ".json"):
                category = example["category"]
                if counts[category] >= 2:
                    continue
                counts[category] += 1
                oracle = example["memory_ids"]
                swapped = [next(mid for mid, m in memories.items() if m["category"] == memories[target]["category"]
                                and m["answer"] != memories[target]["answer"] and mid not in oracle) for target in oracle]
                banks = dict(original_k16=ref.candidate_ids(example, list(memories), identity["k"]),
                             oracle_only=oracle, swapped_same_category=swapped, none=[], text_oracle=[])
                for mode, ids in banks.items():
                    prompt = ref.prompt_ids(tokenizer, example, [memories[mid] for mid in oracle] if mode == "text_oracle" else None)
                    bank = table.prepare(adapter.layer, ids, active, metadata["scope"], metadata["generation"], identity["k"])
                    telemetry = []
                    def inspect(layer, inputs, output):
                        h, b = inputs
                        if b is None or not b.ids or telemetry:
                            return
                        q = layer.query(layer.norm(h[:, -1:]))
                        weights = ((q @ b.keys.T) / math.sqrt(q.shape[-1])).float().softmax(-1)
                        gate = layer.gate(h[:, -1:]).sigmoid()
                        telemetry.append(dict(gate=float(gate.mean()),
                            correct_attention_mass=float(weights[..., [i for i, mid in enumerate(b.ids) if mid in oracle]].sum()),
                            attention_entropy=float(-(weights * weights.clamp_min(1e-30).log()).sum()),
                            residual_over_hidden=float((output[:, -1:].float()-h[:, -1:].float()).norm()/h[:, -1:].float().norm())))
                    handle = adapter.layer.register_forward_hook(inspect)
                    tokens = torch.tensor([prompt], device=placement["embedding"])
                    start = time.monotonic()
                    try:
                        with adapter.using(bank):
                            output = model.generate(input_ids=tokens, attention_mask=torch.ones_like(tokens),
                                max_new_tokens=32, do_sample=False, eos_token_id=eos,
                                pad_token_id=tokenizer.pad_token_id or eos[0], use_cache=True)
                    finally:
                        handle.remove()
                    generated = output[0, len(prompt):].tolist()
                    answer = tokenizer.decode(generated, skip_special_tokens=True)
                    expected = "; ".join(memories[mid]["answer"] for mid in swapped) if mode == "swapped_same_category" else example["answer"]
                    norm = lambda s: [ref.normalized(v) for v in s.split(";")]
                    row = dict(split=split, id=example["id"], category=category, mode=mode, bank_ids=ids,
                        answer=answer, expected=expected, original_expected=example["answer"],
                        correct=bool(generated and generated[-1] in eos) and norm(answer)==norm(expected),
                        telemetry=telemetry, seconds=time.monotonic()-start)
                    records.append(row)
                    log.write(json.dumps(row)+"\n"); log.flush()
                    print(json.dumps(row), flush=True)
    groups = defaultdict(list)
    for row in records:
        groups[row["split"] + "/" + row["mode"]].append(row)
    report = {key: dict(correct=sum(r["correct"] for r in rows), total=len(rows)) for key, rows in groups.items()}
    (args.out / "summary.json").write_text(json.dumps(report, indent=2)+"\n")
    adapter.close()
    for hook in hooks:
        hook.remove()


if __name__ == "__main__":
    main()
