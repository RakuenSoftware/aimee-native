#!/usr/bin/env python3
"""Summarize a complete frozen continuation run, including failed transfers."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('directory',type=Path)
    ap.add_argument('--plan',type=Path,required=True)
    args=ap.parse_args()
    records=[json.loads(s) for s in (args.directory/'results.jsonl').read_text().splitlines()]
    plan=json.loads(args.plan.read_text())
    if [r['id'] for r in records]!=[j['id'] for j in plan['jobs']]:
        raise ValueError('evaluation missing, repeated, or out-of-order trials')
    grouped=defaultdict(list)
    by_case=defaultdict(dict)
    for r in records:
        grouped[(r['split'],r['mode'],r['condition'])].append(r)
        by_case[r['case']][r['condition']]=r
    scores=[]
    for (split,mode,condition),group in sorted(grouped.items()):
        scores.append(dict(split=split,mode=mode,condition=condition,count=len(group),
                           correct_answers=sum(r['answer_correct'] is True for r in group) if group[0]['answer_scored'] and split!='isolation' else None,
                           target_first_tokens=sum(r['exact_target_first_token'] for r in group),
                           contains_amber=sum(r['contains_amber'] for r in group),
                           truncated=sum(r['truncated'] for r in group)))
    cases=[]
    for name,arms in by_case.items():
        a,b=arms['trigger_only'],arms['removed']
        case=dict(id=name,split=a['split'],mode=a['mode'],
                  removal_generated_tokens_equal=a['generated_tokens']==b['generated_tokens'],
                  removal_probability_delta=b['target_probability']-a['target_probability'],
                  memory_tokens_text=len(arms['text']['prompt_tokens'])-len(arms['none']['prompt_tokens']),
                  memory_tokens_latent=len(arms['latent']['prompt_tokens'])-len(arms['none']['prompt_tokens']),
                  arms={arm:{k:r[k] for k in ['target_probability','target_rank','generated_text','answer_correct','truncated']}
                        for arm,r in arms.items()})
        if a['split']=='isolation':
            case['installed_patch_matches_trigger_only']=(a['generated_tokens']==arms['latent']['generated_tokens']
                and a['target_probability']==arms['latent']['target_probability'])
        cases.append(case)
    logits=[]
    for name in ['fit_chat','user_prefix_holdout_1']:
        raw={arm:(args.directory/(name+'__'+arm+'.f32')).read_bytes()
             for arm in ['trigger_only','latent','removed']}
        logits.append(dict(case=name,entries=len(raw['removed'])//4,
            removal_byte_identical=raw['trigger_only']==raw['removed'],
            patch_changes_logits=raw['trigger_only']!=raw['latent'],
            sha256={k:hashlib.sha256(v).hexdigest() for k,v in raw.items()}))
    result=dict(trials=len(records),scores=scores,cases=cases,logits=logits,
                all_trials_restored=all(r['rows_restored'] and r['fresh_context'] for r in records),
                all_removal_continuations_equal=all(c['removal_generated_tokens_equal'] and c['removal_probability_delta']==0 for c in cases),
                scope='one synthetic fact; one warm-started multi-context optimization; fixed-order inference')
    (args.directory/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(trials=len(records),scores=scores,logits=logits,
                          all_removal_continuations_equal=result['all_removal_continuations_equal']),indent=2))


if __name__=='__main__':
    main()
