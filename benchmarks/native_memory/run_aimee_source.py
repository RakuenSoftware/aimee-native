#!/usr/bin/env python3
"""One actual Aimee record -> one latent value -> answers with no fact text."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import torch

from checkpoint_runtime import inspect_checkpoint, load_model


def parse_source(payload):
    record = payload["memory"]
    if not isinstance(record["id"], int) or not payload.get("store"):
        raise ValueError("Aimee get record and store required")
    match = re.fullmatch(r"The beacon color of (unit-[a-f0-9]+) is ([A-Za-z]+)\.", record["content"])
    if not match:
        raise ValueError("this bounded POC expects the synthetic beacon fact")
    entity, answer = match.groups()
    return record, entity, answer


def questions(entity):
    return [f"What is the beacon color of {entity}?", f"Give {entity}'s beacon color."], [
        f"For {entity}, which value is recorded under beacon color?",
        f"Which beacon color is assigned to {entity}?",
        f"Tell me the recorded beacon color for {entity}.",
        f"What color should the beacon on {entity} display?",
        f"I need {entity}'s beacon color. What is it?",
        f"Look up the beacon color associated with {entity}."]


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2)+"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="immutable implementation of the trained interface")
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--aimee-record", type=Path, required=True, help="unmodified aimee --json memory get output")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=240, help="smoke override; real POC budget is 240")
    parser.add_argument("--compiler", choices=["optimize", "cached"], default="optimize")
    args = parser.parse_args()
    if args.steps < 1:
        parser.error("positive compilation budget required")
    args.out.mkdir(parents=True, exist_ok=False)
    payload = json.loads(args.aimee_record.read_text())
    record, entity, answer = parse_source(payload)
    train_queries, eval_queries = questions(entity)
    r = inspect_checkpoint(args.source, args.train)
    matching = [(i,m) for i,m in enumerate(r.metadata["memories"]) if m["entity"]==entity]
    if len(matching)!=1:
        raise ValueError("a matching original entity is required for the old-value control")
    row_index, old_memory = matching[0]
    if args.compiler=="optimize" and any(m["answer"].casefold()==answer.casefold() for m in r.metadata["memories"]):
        raise ValueError("Aimee value must be new to the trained memory table")
    if args.compiler=="cached" and old_memory["content"] != record["content"]:
        raise ValueError("cached projection must exactly match Aimee's authoritative content")
    write_json(args.out/"source-record.json", payload)
    provenance = dict(memory_id=record["id"], store=payload["store"], scope=record["scope"],
        content_sha256=hashlib.sha256(record["content"].encode()).hexdigest(),
        source_record_sha256=r.ref.digest(args.aimee_record), checkpoint=r.compatibility, compiler=args.compiler,
        implementation_sha256={name:r.ref.digest(Path(__file__).with_name(name)) for name in
                               ["run_aimee_source.py", "checkpoint_runtime.py"]})
    write_json(args.out/"provenance.json", provenance)
    load_model(r)
    r.adapter.layer.requires_grad_(False)
    parameter = next(r.adapter.layer.parameters())
    original = r.saved["values"]["values"][row_index:row_index+1].detach().to(parameter.device, parameter.dtype)
    control_mode = "native_original_value"
    wrong_value, wrong_answer = original, old_memory["answer"]
    if args.compiler=="cached":
        wrong_index, wrong_memory = next((i,m) for i,m in enumerate(r.metadata["memories"])
            if m["category"]==old_memory["category"] and m["answer"]!=answer)
        wrong_value = r.saved["values"]["values"][wrong_index:wrong_index+1].detach().to(parameter.device, parameter.dtype)
        wrong_answer, control_mode = wrong_memory["answer"], "native_wrong_value"
    value = torch.nn.Parameter(original.float().clone())
    optimizer = torch.optim.AdamW([value], lr=0.001, weight_decay=0)
    eos = r.model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    def tokens(query, text=False):
        return r.ref.prompt_ids(r.tokenizer, dict(query=query), [record] if text else None)
    def tensor(ids):
        return torch.tensor([ids], device=r.input_device)
    for query in train_queries+eval_queries:
        decoded = r.tokenizer.decode(tokens(query))
        if record["content"] in decoded or answer.casefold() in decoded.casefold():
            raise ValueError("memory answer leaked into native prompt")
    torch.manual_seed(4817)
    r.model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant":False})
    r.model.train()
    target = r.tokenizer.encode(answer, add_special_tokens=False)+[eos[0]]
    with (args.out/"compilation.jsonl").open("x") as log:
        for step in range(args.steps if args.compiler=="optimize" else 0):
            prompt = tokens(train_queries[step % len(train_queries)])
            bank = r.adapter.layer.prepare([record["id"]], value.to(parameter.dtype), 1)
            optimizer.zero_grad(set_to_none=True)
            with r.adapter.using(bank):
                loss = r.model(input_ids=tensor(prompt+target), labels=tensor([-100]*len(prompt)+target), use_cache=False).loss
                if not torch.isfinite(loss):
                    raise ValueError("nonfinite compilation loss")
                loss.backward()
            if any(p.grad is not None for p in list(r.model.parameters())+list(r.adapter.layer.parameters())):
                raise RuntimeError("frozen base/interface received gradients")
            norm = torch.nn.utils.clip_grad_norm_([value], 1.0)
            if not torch.isfinite(norm):
                raise ValueError("nonfinite compilation gradient")
            optimizer.step()
            row = dict(step=step, loss=float(loss.detach()), gradient_norm=float(norm), memory_id=record["id"])
            log.write(json.dumps(row)+"\n"); log.flush()
            if step % 20==0:
                print(json.dumps(row), flush=True)
    artifact = args.out/"aimee-memory-value.pt"
    torch.save(dict(provenance=provenance, value=value.detach().cpu()), artifact)
    # Reload the actual disposable artifact used for inference.
    loaded = torch.load(artifact, map_location="cpu", weights_only=True)
    if loaded["provenance"] != provenance:
        raise ValueError("source/model provenance mismatch")
    r.model.gradient_checkpointing_disable()
    r.model.eval()
    records = []
    prompts = []
    with torch.no_grad(), (args.out/"evaluation.jsonl").open("x") as log:
        native = r.adapter.layer.prepare([record["id"]], loaded["value"].to(parameter.device, parameter.dtype), 1)
        wrong = r.adapter.layer.prepare([record["id"]], wrong_value, 1)
        empty = r.adapter.layer.prepare([], original[:0], 1)
        for index, query in enumerate(eval_queries):
            plain = tokens(query)
            prompts.append(dict(id=index, query=query, native_prompt=r.tokenizer.decode(plain), token_ids=plain))
            for mode, bank in [("none", None), ("text_control", None), ("native_disabled", None),
                               ("native_aimee", native), (control_mode, wrong), ("native_empty", empty)]:
                prompt = tokens(query, text=mode=="text_control")
                with r.adapter.using(bank):
                    output = r.model.generate(input_ids=tensor(prompt), attention_mask=torch.ones_like(tensor(prompt)),
                        max_new_tokens=32, do_sample=False, eos_token_id=eos,
                        pad_token_id=r.tokenizer.pad_token_id or eos[0], use_cache=True)
                generated = output[0, len(prompt):].tolist()
                actual = r.tokenizer.decode(generated, skip_special_tokens=True)
                terminated = bool(generated and generated[-1] in eos)
                row = dict(id=index, mode=mode, answer=actual, expected=answer,
                    correct=terminated and r.ref.normalized(actual)==r.ref.normalized(answer),
                    control_value_correct=terminated and r.ref.normalized(actual)==r.ref.normalized(wrong_answer),
                    terminated=terminated, generated_ids=generated, prompt_tokens=len(prompt),
                    added_memory_tokens=len(prompt)-len(plain), prompt_sha256=hashlib.sha256(json.dumps(prompt).encode()).hexdigest(),
                    memory_ids=list(bank.ids) if bank else [])
                records.append(row)
                log.write(json.dumps(row)+"\n"); log.flush()
                print(json.dumps(row), flush=True)
    write_json(args.out/"native-prompts.json", prompts)
    indexed = {(row["id"],row["mode"]):row for row in records}
    scores = {mode:sum(row["correct"] for row in records if row["mode"]==mode) for mode in {row["mode"] for row in records}}
    paired_successes = sum(indexed[(i,"native_aimee")]["correct"] and not indexed[(i,"none")]["correct"]
                           and not indexed[(i,control_mode)]["correct"] for i in range(len(eval_queries)))
    checks = dict(no_memory_text_in_native_prompts=True,
        zero_added_memory_tokens=all(row["added_memory_tokens"]==0 for row in records if row["mode"]=="native_aimee"),
        prompt_parity=all(indexed[(i,"native_aimee")]["prompt_sha256"]==indexed[(i,"none")]["prompt_sha256"] for i in range(len(eval_queries))),
        disabled_and_empty_parity=all(indexed[(i,mode)]["generated_ids"]==indexed[(i,"none")]["generated_ids"] for i in range(len(eval_queries)) for mode in ["native_disabled","native_empty"]),
        base_and_interface_frozen=True, source_is_aimee_readback=True)
    write_json(args.out/"summary.json", dict(question="Can native memory consume an Aimee-authoritative fact absent from textual context?",
        memory_id=record["id"], source_store=payload["store"], source_content_hash=provenance["content_sha256"],
        correct_by_mode=scores, queries_per_mode=len(eval_queries), paired_native_successes=paired_successes,
        proof_of_concept="demonstrated_on_this_fact" if paired_successes and all(checks.values()) else "not_demonstrated",
        checks=checks, compiler=args.compiler, compilation_steps=args.steps if args.compiler=="optimize" else 0,
        trainable_parameters=value.numel() if args.compiler=="optimize" else 0,
        speed_is_acceptance_gate=False, text_parity_is_acceptance_gate=False,
        limitations=["One synthetic fact in actual Aimee storage, not a broad memory-quality claim.",
                     "Optimization uses offline Aimee supervision; cached mode reuses an exact-content-matched learned projection.",
                     "No retrieval-quality, latency, image-format or production-readiness conclusion."]))
    r.adapter.close()
    for hook in r.hooks:
        hook.remove()


if __name__=="__main__":
    main()
