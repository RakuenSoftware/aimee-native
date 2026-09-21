#!/usr/bin/env python3
"""Score the footer counterexperiment and verify its byte-level controls."""
import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'multicontext'))
from train_multi import NativeQuantizer


def main():
    ap=argparse.ArgumentParser()
    for name in ['run','evaluation','frozen','inspection','codec','hash-helper']:
        ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--initialization',type=Path)
    args=ap.parse_args()
    hashes=json.loads((args.frozen/'sha256.json').read_text())
    for name,digest in hashes.items():
        assert hashlib.sha256((args.frozen/name).read_bytes()).hexdigest()==digest
    config=json.loads((args.run/'configuration.json').read_text())
    assert config['training_sha256']==hashes['training.json']
    expected_init=hashlib.sha256(args.initialization.read_bytes()).hexdigest() if args.initialization else hashes['cold-rows.json']
    assert config['warm_start_sha256']==expected_init
    result=json.loads((args.run/'result.json').read_text())
    assert result['stop_reason']!='intermediate_training_checkpoint'
    steps=[json.loads(s) for s in (args.run/'steps.jsonl').read_text().splitlines()]
    assert steps[-1]==result['last_record'] and len(steps)==result['steps']
    overlay=json.loads((args.run/'overlay.json').read_text())
    values=np.array([r['values'] for r in overlay['rows']],dtype=np.float32)
    _,encoded=NativeQuantizer(args.codec).quantize(values)
    assert encoded.tobytes()==(args.run/'payload.iq4nl').read_bytes()
    assert hashlib.sha256(encoded.tobytes()).hexdigest()==result['payload_sha256']
    table=json.loads(args.inspection.read_text())['table']
    with open(table['shard'],'rb') as f:
        for row in json.loads((args.run/'original-rows.json').read_text()):
            f.seek(table['data_offset']+row['id']*90)
            assert hashlib.sha256(f.read(90)).hexdigest()==row['sha256']
    plan=json.loads((args.frozen/'evaluation.json').read_text())
    records=[json.loads(s) for s in (args.evaluation/'results.jsonl').read_text().splitlines()]
    assert len(records)==32 and [r['id'] for r in records]==[j['id'] for j in plan['jobs']]
    groups=defaultdict(list);cases=defaultdict(dict)
    for r,j in zip(records,plan['jobs']):
        assert r['prompt_tokens']==j['expected_prompt_tokens']
        assert r['fresh_context'] and r['rows_restored']
        groups[(r['split'],r['condition'])].append(r)
        cases[r['case']][r['condition']]=r
    scores=[dict(split=k[0],condition=k[1],count=len(v),correct=sum(r['answer_correct'] for r in v),
                 truncated=sum(r['truncated'] for r in v),contains_amber=sum(r['contains_amber'] for r in v))
            for k,v in sorted(groups.items())]
    details=[]
    for name,arms in cases.items():
        a,b=arms['none'],arms['removed']
        assert a['generated_tokens']==b['generated_tokens']
        assert a['target_probability']==b['target_probability']
        assert a['prompt_tokens']==arms['latent']['prompt_tokens']==b['prompt_tokens']
        details.append(dict(id=name,split=a['split'],memory_tokens_latent=0,
            memory_tokens_text=len(arms['text']['prompt_tokens'])-len(a['prompt_tokens']),
            arms={arm:{k:r[k] for k in ['target_probability','target_rank','generated_text','answer_correct','truncated']}
                  for arm,r in arms.items()}))
    logits=[]
    for name in ['fit_footer','footer_holdout_1']:
        raw={arm:(args.evaluation/(name+'__'+arm+'.f32')).read_bytes() for arm in ['none','latent','removed']}
        assert raw['none']==raw['removed']
        logits.append(dict(case=name,entries=len(raw['none'])//4,removal_byte_identical=True,
                           patch_changes_logits=raw['none']!=raw['latent'],
                           sha256={k:hashlib.sha256(v).hexdigest() for k,v in raw.items()}))
    spec=importlib.util.spec_from_file_location('hash_helper',args.hash_helper)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    metadata=json.loads(args.inspection.read_text())['metadata']
    selected=set(plan['identity']['row_ids'])
    extra_hits=[]
    for record in records:
        prompt=record['prompt_tokens'];seq=prompt+record['generated_tokens']
        hits=[i for i in range(len(prompt),len(seq)) if set(helper.rows(seq[:i+1],metadata)) & selected]
        if hits: extra_hits.append(dict(id=record['id'],positions=hits))
    output=dict(trials=32,scores=scores,cases=details,logits=logits,
                protocol_hashes_intact=True,original_selected_disk_rows_unchanged=True,
                encoded_payload_reproduces_exactly=True,all_contexts_fresh_and_rows_restored=True,
                all_removal_continuations_equal=True,all_latent_prompts_identical_to_no_memory=True,
                selected_row_hits_in_generated_continuations=extra_hits,
                interpretation='process-local substitution at a natural template lookup; no direct-row API')
    (args.evaluation/'analysis-verification.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(dict(scores=scores,logits=logits),indent=2))


if __name__=='__main__': main()
