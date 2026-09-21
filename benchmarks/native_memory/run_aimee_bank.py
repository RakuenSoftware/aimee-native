#!/usr/bin/env python3
"""Tiny Aimee multi-memory working-set test. Uses cached projections only."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import torch

from bank_matrix import banks, score
from checkpoint_runtime import inspect_checkpoint, load_model


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2)+"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    r = inspect_checkpoint(args.source, args.train)
    sources = json.loads(args.records.read_text())
    roles = ["target", "d1", "d2", "d3", "wrong"]
    if set(sources)!=set(roles):
        raise ValueError("exactly the five predeclared source roles are required")
    selected, provenance = {}, {}
    heldout = r.ref.read_fixture(r.fixtures, "heldout.json")
    for role in roles:
        payload = sources[role]
        memory = payload["memory"]
        matches = [(i,m) for i,m in enumerate(r.metadata["memories"]) if m["content"]==memory["content"]]
        if len(matches)!=1:
            raise ValueError("Aimee content must exactly match one existing projection")
        index, learned = matches[0]
        own_query = next(q["query"] for q in heldout if q["memory_ids"]==[learned["memory_id"]])
        selected[role] = dict(memory=memory, learned=learned, index=index, query=own_query)
        provenance[role] = dict(aimee_memory_id=memory["id"], store=payload["store"], scope=memory["scope"],
            compiled_memory_id=learned["memory_id"], content_sha256=hashlib.sha256(memory["content"].encode()).hexdigest())
    if len({s["memory"]["id"] for s in selected.values()})!=5:
        raise ValueError("source roles must refer to distinct Aimee memories")
    if any((p["store"],p["scope"])!=(provenance["target"]["store"],provenance["target"]["scope"]) for p in provenance.values()):
        raise ValueError("mixed source scope")
    target = selected["target"]["learned"]["answer"]
    if target!="teal" or any(selected[role]["learned"]["answer"]==target for role in roles[1:]):
        raise ValueError("unexpected target/distractor values")
    query = selected["target"]["query"]
    write_json(args.out/"sources.json", sources)
    write_json(args.out/"provenance.json", dict(records_sha256=r.ref.digest(args.records), records=provenance,
        checkpoint=r.compatibility, implementation={name:r.ref.digest(Path(__file__).with_name(name)) for name in
        ["run_aimee_bank.py", "bank_matrix.py", "checkpoint_runtime.py"]}, training_steps=0))
    load_model(r)
    r.adapter.layer.requires_grad_(False).eval()
    r.model.requires_grad_(False).eval()
    p = next(r.adapter.layer.parameters())
    vectors = {role:r.saved["values"]["values"][s["index"]].detach().to(p.device,p.dtype) for role,s in selected.items()}
    eos = r.model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos,int) else eos
    first_scores = {}
    logs = (args.out/"generations.jsonl").open("x")
    def generate(label, question, mapping):
        ids = [selected[identity]["memory"]["id"] for identity,_ in mapping]
        payload_ids = [selected[payload]["memory"]["id"] for _,payload in mapping]
        bank_vectors = torch.stack([vectors[payload] for _,payload in mapping]) if mapping else vectors["target"][None,:][:0]
        bank = r.adapter.layer.prepare(ids, bank_vectors, 1)
        prompt = r.ref.prompt_ids(r.tokenizer, dict(query=question))
        decoded = r.tokenizer.decode(prompt)
        if any(s["memory"]["content"] in decoded or s["learned"]["answer"].casefold() in decoded.casefold() for s in selected.values()):
            raise ValueError("memory content/answer leaked into the prompt")
        telemetry = []
        def inspect(layer, inputs, output):
            hidden, current = inputs
            if current is None or not current.ids:
                return
            h = hidden[:,-1:]
            q = layer.query(layer.norm(h.to(layer.query.weight.dtype)))
            weights = ((q @ current.keys.T)/math.sqrt(q.shape[-1])).float().softmax(-1)
            telemetry.append(dict(phase="prefill" if hidden.shape[1]>1 else "decode",
                attention=weights.flatten().tolist(), memory_ids=list(current.ids),
                gate=float(layer.gate(h.to(layer.query.weight.dtype)).sigmoid().mean()),
                residual_over_hidden=float((output[:,-1:].float()-h.float()).norm()/h.float().norm().clamp_min(1e-12))))
        handle = r.adapter.layer.register_forward_hook(inspect)
        try:
            tensor = torch.tensor([prompt],device=r.input_device)
            with r.adapter.using(bank):
                result = r.model.generate(input_ids=tensor,attention_mask=torch.ones_like(tensor),
                    max_new_tokens=32,do_sample=False,eos_token_id=eos,pad_token_id=r.tokenizer.pad_token_id or eos[0],
                    use_cache=True,return_dict_in_generate=True,output_scores=True)
        finally:
            handle.remove()
        generated = result.sequences[0,len(prompt):].tolist()
        answer = r.tokenizer.decode(generated,skip_special_tokens=True)
        if label in ["C","D"]:
            first_scores[label] = result.scores[0].detach().float().cpu()
        row = dict(case=label,query=question,answer=answer,terminated=bool(generated and generated[-1] in eos),
            generated_ids=generated,bank_ids=ids,payload_source_ids=payload_ids,prompt_tokens=len(prompt),
            prompt_sha256=hashlib.sha256(json.dumps(prompt).encode()).hexdigest(),native_prompt=decoded,
            token_ids=prompt,added_memory_tokens=0,telemetry=telemetry)
        logs.write(json.dumps(row)+"\n"); logs.flush()
        print(json.dumps({k:v for k,v in row.items() if k not in ["token_ids","native_prompt","telemetry"]}),flush=True)
        return row
    with torch.inference_mode():
        validations = []
        for role in roles:
            row = generate("singleton_"+role,selected[role]["query"],[(role,role)])
            expected = selected[role]["learned"]["answer"]
            validations.append(dict(role=role,expected=expected,answer=row["answer"],
                passed=row["terminated"] and r.ref.normalized(row["answer"])==r.ref.normalized(expected)))
        write_json(args.out/"singleton-validation.json",validations)
        if not all(v["passed"] for v in validations):
            write_json(args.out/"summary.json",dict(status="precondition_failed",validations=validations,
                reason="At least one supplied projection did not revalidate alone; A–F not run."))
        else:
            baseline = generate("none",query,[])
            results = {}
            for case,mapping in banks().items():
                row = generate(case,query,mapping)
                results[case] = dict(answer=row["answer"],bank_ids=row["bank_ids"],payload_source_ids=row["payload_source_ids"],
                    generated_ids=row["generated_ids"],prompt_sha256=row["prompt_sha256"],
                    **score(case,row["answer"],target,row["terminated"]))
            prompt_parity = all(row["prompt_sha256"]==baseline["prompt_sha256"] for row in results.values())
            order = dict(generated_tokens_equal=results["C"]["generated_ids"]==results["D"]["generated_ids"],
                first_token_scores_exact=torch.equal(first_scores["C"],first_scores["D"]),
                first_token_score_max_abs_delta=float((first_scores["C"]-first_scores["D"]).abs().max()))
            passed = all(row["passed"] for row in results.values()) and prompt_parity and order["generated_tokens_equal"]
            composition = dict(status="not_run",reason="A–F must all pass first")
            if passed:
                q = f"Give the preferred drink of {selected['d1']['learned']['entity']}, then the home city of {selected['d2']['learned']['entity']}. Separate the two values with a semicolon."
                expected = selected["d1"]["learned"]["answer"]+"; "+selected["d2"]["learned"]["answer"]
                both = generate("composition_both",q,[("d1","d1"),("d2","d2")])
                only1 = generate("composition_only_d1",q,[("d1","d1")])
                only2 = generate("composition_only_d2",q,[("d2","d2")])
                correct = lambda row: row["terminated"] and r.ref.value_match(row["answer"],expected)
                composition = dict(status="complete",expected=expected,both=both["answer"],only_d1=only1["answer"],only_d2=only2["answer"],
                    passed=correct(both) and not correct(only1) and not correct(only2))
            write_json(args.out/"summary.json",dict(status="complete",singleton_validation=validations,
                target=target,query=query,results=results,no_memory_answer=baseline["answer"],
                matrix_passed=passed,order=order,prompt_parity=prompt_parity,
                zero_memory_tokens=True,training_steps=0,trainable_parameters=0,composition=composition,
                limits="One target question, one fixed distractor set; no general accuracy or speed claim"))
    logs.close()
    r.adapter.close()
    for hook in r.hooks:
        hook.remove()


if __name__=="__main__":
    main()
