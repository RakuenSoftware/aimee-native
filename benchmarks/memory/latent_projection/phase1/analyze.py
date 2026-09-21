#!/usr/bin/env python3
"""Summarize actual engine results without treating replica scores as recall."""
import argparse
import json
from pathlib import Path
import struct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('directory', type=Path)
    args = ap.parse_args()
    records = [json.loads(line) for line in (args.directory/'results.jsonl').read_text().splitlines()]
    by_id = {r['id']: r for r in records}
    cases = []
    for name in ['train', 'heldout1', 'heldout2', 'heldout3', 'heldout4', 'cloze1', 'cloze2', 'cloze3']:
        arms = {arm: by_id[name+'__'+arm] for arm in ['none','text','trigger_only','latent','removed']}
        row = dict(case=name)
        for arm, result in arms.items():
            row[arm] = dict(probability=result['target_probability'], rank=result['target_rank'],
                            text=result['generated_text'], tokens=len(result['prompt_tokens']),
                            exact_target_token=result['generated_tokens'][0] == 65326,
                            prefill_seconds=result['prefill_seconds'])
        row['memory_tokens_text'] = row['text']['tokens'] - row['none']['tokens']
        row['memory_tokens_latent'] = row['latent']['tokens'] - row['none']['tokens']
        row['removal_tokens_equal'] = arms['trigger_only']['generated_tokens'] == arms['removed']['generated_tokens']
        row['removal_probability_delta'] = arms['removed']['target_probability'] - arms['trigger_only']['target_probability']
        cases.append(row)
    controls = {}
    for name in ['unrelated','sister']:
        a, b = by_id[name+'__none'], by_id[name+'__latent']
        controls[name] = dict(tokens_equal=a['generated_tokens']==b['generated_tokens'],
                              probability_delta=b['target_probability']-a['target_probability'])
    logits = {}
    for name in ['trigger_only','latent','removed']:
        data=(args.directory/('train__'+name+'.f32')).read_bytes()
        logits[name]=struct.unpack('<'+'f'*(len(data)//4),data)
    if len({len(v) for v in logits.values()}) != 1:
        raise ValueError('logit lengths differ')
    result = dict(cases=cases, controls=controls,
                  diagnostics=[r for r in records if r['id'].startswith('diagnostic_')],
                  training_removal_logits_max_abs_delta=max(abs(a-b) for a,b in zip(logits['trigger_only'],logits['removed'])),
                  training_overlay_logits_max_abs_delta=max(abs(a-b) for a,b in zip(logits['trigger_only'],logits['latent'])),
                  actual_engine='llama.cpp Vulkan/CPU', compiler_score_is_not_acceptance=True,
                  limitations=['One fact and one run.', 'Raw next-token/short-continuation evaluation.',
                               'No general chat answer-accuracy or throughput claim.'])
    (args.directory/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
