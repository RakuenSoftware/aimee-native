#!/usr/bin/env python3
"""Serial P0 training/evaluation with oracle IDs and a frozen HF Qwen model.

CE uses synthetic authoritative answer labels. Text-teacher quality is measured
as a separate arm; KL distillation and learned cue routing are not implemented.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import time

import torch
import transformers
from transformers import AutoConfig, AutoTokenizer, Qwen3_5ForCausalLM, Qwen3_5ForConditionalGeneration

from engram import FrozenQwenEngram, OracleValues
from placement import place
from frozen_int8 import quantize_frozen_linears


SYSTEM = "Answer using the available memory. Return only the requested value or values. If unknown, return unknown."


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 << 20), b""):
            result.update(chunk)
    return result.hexdigest()


def read_fixture(directory, filename):
    hashes = json.loads((directory / "sha256.json").read_text())
    if digest(directory / filename) != hashes[filename]:
        raise ValueError(f"frozen fixture changed: {filename}")
    return json.loads((directory / filename).read_text())


def candidate_ids(example, memory_ids, k, policy="distractors"):
    correct = example["memory_ids"]
    if len(correct) > k:
        raise ValueError("K smaller than oracle answer set")
    if policy == "oracle":
        # No ordinal cue: do not give composition answers in query order.
        correct = list(correct)
        random.Random(example["id"]).shuffle(correct)
        return correct
    if policy != "distractors":
        raise ValueError("unknown bank policy")
    seed = int(hashlib.sha256(example["id"].encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    others = [mid for mid in memory_ids if mid not in correct]
    bank = correct + rng.sample(others, min(k - len(correct), len(others)))
    rng.shuffle(bank)
    return bank


def prompt_ids(tokenizer, example, memories=None):
    query = example["query"]
    if memories is not None:
        query += "\n\nAuthoritative memory:\n" + "\n".join(m["content"] for m in memories)
    # No IDs, synthetic triggers, latent descriptions or answer text are added
    # to native/none/disabled prompts. Bank IDs travel outside tokenization.
    return tokenizer.apply_chat_template(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": query}],
        tokenize=True, return_dict=False, add_generation_prompt=True, enable_thinking=False)


def normalized(text):
    return " ".join(text.strip().casefold().split())


def value_match(answer, expected):
    # Ordered, exact values; ignore only whitespace surrounding the requested
    # delimiter. Preserve the legacy whole-string score in the result too.
    return [normalized(v) for v in answer.split(";")] == [normalized(v) for v in expected.split(";")]


def swapped_ids(example, ids, memories):
    replacements = {}
    for target in example["memory_ids"]:
        replacements[target] = next(mid for mid, memory in memories.items()
            if memory["active"] and memory["category"] == memories[target]["category"]
            and memory["answer"] != memories[target]["answer"] and mid not in example["memory_ids"])
    return list(dict.fromkeys(replacements.get(mid, mid) for mid in ids)), "; ".join(
        memories[replacements[mid]]["answer"] for mid in example["memory_ids"])


def summary(records, corpus_size, total_heldout):
    groups = defaultdict(list)
    for row in records:
        groups[row["mode"]].append(row)
    accuracy = {mode: sum(r["correct"] for r in rows) / len(rows) for mode, rows in groups.items()}
    strict_accuracy = {mode: sum(r.get("strict_correct", r["correct"]) for r in rows) / len(rows)
                       for mode, rows in groups.items()}
    by_category = {}
    for mode, rows in groups.items():
        categories = {r["category"] for r in rows}
        by_category[mode] = {c: sum(r["correct"] for r in rows if r["category"] == c) /
                             sum(r["category"] == c for r in rows) for c in categories}
    reference = accuracy.get("text", 0)
    relative = accuracy.get("native", 0) / reference if reference else None
    complete = len(groups.get("native", [])) == total_heldout and corpus_size >= 100
    composition = by_category.get("native", {}).get("composition", 0)
    composition_text = by_category.get("text", {}).get("composition", 0)
    indexed = {(r["id"], r["mode"]): r for r in records}
    baseline = groups.get("none", [])
    parity = bool(baseline) and all(
        indexed[(r["id"], mode)]["generated_ids"] == r["generated_ids"]
        for r in baseline for mode in ("native_disabled", "native_empty"))
    prompt_parity = bool(baseline) and all(
        indexed[(r["id"], mode)]["prompt_sha256"] == r["prompt_sha256"]
        for r in baseline for mode in ("native_disabled", "native", "native_empty", "native_distractors", "native_swapped"))
    checks = dict(full_evaluation=complete, text_baseline_nonzero=reference > 0,
                  disabled_and_empty_parity=parity, native_prompt_parity=prompt_parity,
                  relative_accuracy=relative is not None and relative >= .95,
                  composition=composition_text > 0 and composition >= .95 * composition_text,
                  native_zero_added_tokens=all(r["added_prompt_tokens"] == 0 for r in groups.get("native", [])))
    return dict(accuracy=accuracy, strict_string_accuracy=strict_accuracy,
                scoring="ordered semicolon-delimited exact values, case/whitespace normalized, EOS required",
                accuracy_by_category=by_category, native_over_text=relative,
                checks=checks, stage_a_accuracy_gate="pass" if all(checks.values()) else "fail_or_incomplete",
                limitations=["Accuracy gate alone does not establish update, deletion or scope noninterference.",
                             "Research timings are not optimized serving throughput measurements.",
                             "Held-out query forms use trained memories; this is not writer-network generalization."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["train", "evaluate"])
    parser.add_argument("--model", required=True, help="HF checkpoint directory or repository, not a GGUF")
    parser.add_argument("--revision", help="Required immutable revision for remote model repositories")
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--placement", type=Path, help="Explicit static CPU/GPU placement JSON")
    parser.add_argument("--gradient-checkpointing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--base-quantization", choices=["none", "int8_per_row_v1"], default="none")
    parser.add_argument("--dtype", choices=["float32", "bfloat16", "float16"], default="bfloat16")
    parser.add_argument("--adapter-dtype", choices=["base", "float32"], default="base")
    parser.add_argument("--bank-policy", choices=["distractors", "oracle"], default="distractors")
    parser.add_argument("--value-width", type=int, default=2048)
    parser.add_argument("--attention-width", type=int, default=256)
    parser.add_argument("--after-block", type=int, default=1)
    parser.add_argument("--k", type=int, default=16)
    parser.add_argument("--steps", type=int, default=21000,
                        help="Fixed training budget; default is ten epochs of the 1000-memory fixture")
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=4817)
    parser.add_argument("--eval-limit", type=int, default=0)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    args = parser.parse_args()
    if args.model.endswith(".gguf"):
        parser.error("P0 requires a differentiable HF checkpoint; GGUF is not accepted")
    if not Path(args.model).is_dir() and (not args.revision or len(args.revision) != 40):
        parser.error("pin remote model to a full commit hash using --revision")
    if args.action == "evaluate" and args.checkpoint is None:
        parser.error("evaluation requires --checkpoint")
    if args.k < 2 or args.steps < 1 or args.eval_limit < 0 or args.max_new_tokens < 1:
        parser.error("invalid experiment bounds")
    args.out.mkdir(parents=True, exist_ok=False)
    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    metadata = read_fixture(args.fixtures, "memories.json")
    memories = {m["memory_id"]: m for m in metadata["memories"]}
    active = {mid for mid, m in memories.items() if m["active"]}
    memory_ids = list(memories)
    config = AutoConfig.from_pretrained(args.model, revision=args.revision, trust_remote_code=False)
    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision, trust_remote_code=False)
    cls = {"qwen3_5": Qwen3_5ForConditionalGeneration, "qwen3_5_text": Qwen3_5ForCausalLM}.get(config.model_type)
    if cls is None:
        raise ValueError("unexpected architecture")
    model = cls.from_pretrained(args.model, revision=args.revision, dtype=getattr(torch, args.dtype),
                                attn_implementation="eager", trust_remote_code=False).eval()
    model.requires_grad_(False)
    quantized_linears = quantize_frozen_linears(model) if args.base_quantization != "none" else 0
    print(json.dumps(dict(event="base_loaded", quantized_linears=quantized_linears)), flush=True)
    placement = json.loads(args.placement.read_text()) if args.placement else None
    placement_hooks = place(model, placement) if placement else []
    if not placement:
        model.to(args.device)
    input_device = placement["embedding"] if placement else args.device
    adapter = FrozenQwenEngram(model, args.value_width, args.attention_width, args.after_block)
    adapter_dtype = getattr(torch, args.dtype if args.adapter_dtype == "base" else args.adapter_dtype)
    adapter.layer.to(dtype=adapter_dtype)
    table = OracleValues(memory_ids, args.value_width, metadata["scope"], metadata["generation"]).to(
        device=next(adapter.layer.parameters()).device, dtype=adapter_dtype)
    if args.action == "train" and args.gradient_checkpointing:
        # Non-reentrant checkpointing supports frozen inputs and a trainable
        # forward hook. Keep the bank bound through recomputation/backward.
        text_config = getattr(config, "text_config", config)
        if text_config.attention_dropout != 0:
            raise ValueError("P0 checkpointed training requires zero attention dropout")
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.train()
    local_weights = sorted(Path(args.model).glob("*.safetensors")) if Path(args.model).is_dir() else []
    if Path(args.model).is_dir() and not local_weights:
        raise ValueError("local P0 checkpoints must contain safetensors weights")
    identity = dict(model=args.model, revision=args.revision,
                    experiment_format=2,
                    implementation_sha256={name: digest(Path(__file__).with_name(name)) for name in
                        ("engram.py", "placement.py", "frozen_int8.py", "run_p0.py")},
                    local_weight_sha256={p.name: digest(p) for p in local_weights},
                    resolved_commit=getattr(config, "_commit_hash", None),
                    config_sha256=hashlib.sha256(config.to_json_string().encode()).hexdigest(),
                    tokenizer_sha256=hashlib.sha256(tokenizer.backend_tokenizer.to_str().encode()).hexdigest(),
                    chat_template_sha256=hashlib.sha256(str(tokenizer.chat_template).encode()).hexdigest(),
                    fixtures=json.loads((args.fixtures / "sha256.json").read_text()),
                    value_width=args.value_width, attention_width=args.attention_width,
                    after_block=args.after_block, k=args.k, seed=args.seed, dtype=args.dtype,
                    adapter_dtype=args.adapter_dtype, bank_policy=args.bank_policy,
                    placement=placement,
                    gradient_checkpointing=args.gradient_checkpointing,
                    base_quantization=args.base_quantization,
                    transformers=transformers.__version__, torch=str(torch.__version__))
    if args.checkpoint:
        saved = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
        if saved["identity"] != identity:
            raise ValueError("checkpoint model/tokenizer/fixture/architecture identity mismatch")
        adapter.layer.load_state_dict(saved["layer"])
        table.load_state_dict(saved["values"])
    (args.out / "identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    (args.out / "arguments.json").write_text(json.dumps(vars(args), default=str, indent=2) + "\n")
    eos = model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    if not eos:
        raise ValueError("checkpoint must declare answer termination tokens")

    def bank_for(ids):
        return table.prepare(adapter.layer, ids, active, metadata["scope"], metadata["generation"], args.k)

    def tensor(ids):
        return torch.tensor([ids], device=input_device)

    if args.action == "train":
        # This branch never reads heldout.json.
        examples = read_fixture(args.fixtures, "train.json")
        if args.checkpoint is None:
            probe = examples[0]
            inputs = tensor(prompt_ids(tokenizer, probe))
            with torch.no_grad():
                adapter.handle.remove()
                baseline = model(inputs, use_cache=False).logits
                text_model = model.model.language_model if hasattr(model.model, "language_model") else model.model
                adapter.handle = text_model.layers[args.after_block].register_forward_hook(adapter._inject)
                with adapter.using(bank_for(candidate_ids(probe, memory_ids, args.k, args.bank_policy))):
                    zero_initialized = model(inputs, use_cache=False).logits
                parity = torch.equal(baseline, zero_initialized)
                (args.out / "initial-parity.json").write_text(json.dumps(dict(
                    exact_logits=parity, max_abs_delta=float((baseline-zero_initialized).abs().max()),
                    logit_shape=list(baseline.shape)), indent=2)+"\n")
                if not parity:
                    raise RuntimeError("initial native layer changed base logits")
                del baseline, zero_initialized
        optimizer = torch.optim.AdamW(list(adapter.layer.parameters()) + list(table.parameters()), lr=args.lr)
        start = time.monotonic()
        seen = set()
        with (args.out / "training.jsonl").open("x") as log:
            for step in range(args.steps):
                if step % len(examples) == 0:
                    rng.shuffle(examples)
                example = examples[step % len(examples)]
                seen.update(example["memory_ids"])
                ids = candidate_ids(example, memory_ids, args.k, args.bank_policy)
                prompt = prompt_ids(tokenizer, example)
                answer = tokenizer.encode(example["answer"], add_special_tokens=False) + [eos[0]]
                labels = tensor([-100] * len(prompt) + answer)
                optimizer.zero_grad(set_to_none=True)
                with adapter.using(bank_for(ids)):
                    # Base parameters frozen; do NOT use no_grad here. Gradients
                    # must propagate through subsequent frozen transformer blocks.
                    loss = model(input_ids=tensor(prompt + answer), labels=labels, use_cache=False).loss
                    if not torch.isfinite(loss):
                        raise ValueError("non-finite training loss")
                    loss.backward()
                if any(p.grad is not None for p in model.parameters()):
                    raise RuntimeError("base model received gradients")
                grad_norm = torch.nn.utils.clip_grad_norm_(list(adapter.layer.parameters()) + list(table.parameters()), 1.0)
                if not torch.isfinite(grad_norm):
                    raise ValueError("non-finite gradient")
                value_grad_norm = float(table.values.grad.float().norm()) if table.values.grad is not None else None
                output_grad_norm = float(adapter.layer.output.weight.grad.float().norm())
                optimizer.step()
                row = dict(step=step, example=example["id"], loss=float(loss.detach()),
                           grad_norm=float(grad_norm), prompt_tokens=len(prompt), memory_prompt_tokens=0,
                           value_grad_norm=value_grad_norm, output_grad_norm=output_grad_norm,
                           bank_ids=ids, elapsed_seconds=time.monotonic()-start)
                log.write(json.dumps(row) + "\n")
                log.flush()
                print(json.dumps(row), flush=True)
        # Final step is predefined, not chosen on held-out evaluation performance.
        torch.save(dict(identity=identity, layer=adapter.layer.state_dict(), values=table.state_dict()), args.out / "adapter.pt")
        (args.out / "training-summary.json").write_text(json.dumps(dict(
            steps=args.steps, answer_memories_seen=len(seen), total_memories=len(memories),
            train_examples=len(examples), heldout_examples_read=0,
            base_parameters_frozen=True, objective="answer-token CE with synthetic authoritative labels",
            learned_parameters=sum(p.numel() for p in adapter.layer.parameters()) + table.values.numel(),
            elapsed_seconds=time.monotonic()-start), indent=2)+"\n")
    else:
        examples = read_fixture(args.fixtures, "heldout.json")
        total = len(examples)
        if args.eval_limit:
            examples = examples[:args.eval_limit]
        records = []
        with torch.no_grad(), (args.out / "evaluation.jsonl").open("x") as log:
            for example in examples:
                ids = candidate_ids(example, memory_ids, args.k, args.bank_policy)
                admitted = [mid for mid in ids if mid in active]
                plain = prompt_ids(tokenizer, example)
                # Empty bank and wrong-memory controls check whether correct
                # answers are attributable to the intended memory channel.
                modes = ["none", "text", "native_disabled", "native", "native_empty", "native_distractors", "native_swapped"]
                for mode in modes:
                    prompt = prompt_ids(tokenizer, example, [memories[mid] for mid in admitted] if mode == "text" else None)
                    chosen = admitted if mode == "native" else []
                    if mode == "native_distractors":
                        chosen = [mid for mid in admitted if mid not in example["memory_ids"]]
                    expected = example["answer"]
                    if mode == "native_swapped":
                        chosen, expected = swapped_ids(example, admitted, memories)
                    bank = bank_for(chosen) if mode.startswith("native") and mode != "native_disabled" else None
                    # Unhooked modes measure the original architecture. Reattach
                    # after generation so native-disabled includes hook overhead.
                    unhooked = mode in ("none", "text")
                    if unhooked:
                        adapter.handle.remove()
                    before = time.monotonic()
                    try:
                        with adapter.using(bank):
                            output = model.generate(input_ids=tensor(prompt), attention_mask=torch.ones_like(tensor(prompt)),
                                max_new_tokens=args.max_new_tokens, do_sample=False,
                                eos_token_id=eos, pad_token_id=tokenizer.pad_token_id or eos[0], use_cache=True)
                    finally:
                        if unhooked:
                            text = model.model.language_model if hasattr(model.model, "language_model") else model.model
                            adapter.handle = text.layers[args.after_block].register_forward_hook(adapter._inject)
                    if args.device.startswith("cuda"):
                        torch.cuda.synchronize()
                    generated = output[0, len(prompt):].tolist()
                    terminated = bool(generated and generated[-1] in eos)
                    answer = tokenizer.decode(generated, skip_special_tokens=True)
                    row = dict(id=example["id"], category=example["category"], mode=mode, answer=answer,
                               expected=expected, original_expected=example["answer"],
                               correct=terminated and value_match(answer, expected),
                               strict_correct=terminated and normalized(answer) == normalized(expected),
                               terminated=terminated, generated_ids=generated, prompt_tokens=len(prompt),
                               prompt_sha256=hashlib.sha256(json.dumps(prompt).encode()).hexdigest(),
                               added_prompt_tokens=len(prompt)-len(plain), bank_ids=list(bank.ids) if bank else [],
                               seconds=time.monotonic()-before)
                    records.append(row)
                    log.write(json.dumps(row) + "\n")
                    log.flush()
        report = summary(records, len(memories), total)
        (args.out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    adapter.close()
    for handle in placement_hooks:
        handle.remove()


if __name__ == "__main__":
    main()
