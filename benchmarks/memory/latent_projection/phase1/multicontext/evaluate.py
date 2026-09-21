#!/usr/bin/env python3
"""Run frozen native trials and score complete short chat answers."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def normalized_answer(text):
    # Stop markers are transport tokens. Do not discard explanations or refusals.
    return re.sub(r'<\|(?:im_end|endoftext)\|>', '', text).strip().strip('.,!').strip().lower()


def main():
    ap=argparse.ArgumentParser()
    for name in ['plan','inspection','previous','out']:
        ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--overlay',type=Path)
    ap.add_argument('--runner',required=True)
    ap.add_argument('--baseline-only',action='store_true')
    args=ap.parse_args()
    plan=json.loads(args.plan.read_text())
    table=json.loads(args.inspection.read_text())['table']
    args.out.mkdir(exist_ok=False)
    command=[args.runner,plan['identity']['model'],table['shard'],str(table['data_offset']),'26']
    invocation=dict(command=command,plan_sha256=hashlib.sha256(args.plan.read_bytes()).hexdigest(),
                    baseline_only=args.baseline_only,
                    previous_sha256=hashlib.sha256(args.previous.read_bytes()).hexdigest(),
                    overlay_sha256=hashlib.sha256(args.overlay.read_bytes()).hexdigest() if args.overlay else None)
    (args.out/'invocation.json').write_text(json.dumps(invocation,indent=2)+'\n')
    with (args.out/'native.log').open('w') as log, (args.out/'results.jsonl').open('x') as out:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                 stderr=log,text=True,bufsize=1)
        try:
            ready=json.loads(process.stdout.readline())
            if ready.get('event')!='ready': raise RuntimeError(ready)
            (args.out/'ready.json').write_text(json.dumps(ready,indent=2)+'\n')
            print(json.dumps(ready),flush=True)
            for original in plan['jobs']:
                condition=original['condition']
                if args.baseline_only and condition in ['latent','removed']: continue
                job=dict(original)
                if condition=='previous': job['overlay']=str(args.previous.resolve())
                if condition=='latent':
                    if not args.overlay: raise ValueError('overlay is required')
                    job['overlay']=str(args.overlay.resolve())
                # Full distributions for a fitted and a held-out chat prompt.
                if job['case'] in ['fit_chat','user_prefix_holdout_1'] and condition in ['trigger_only','latent','removed']:
                    job['logits_file']=str((args.out/(job['id']+'.f32')).resolve())
                process.stdin.write(json.dumps(job)+'\n');process.stdin.flush()
                response=process.stdout.readline()
                if not response: raise RuntimeError(f'runner stopped at {job["id"]}')
                result=json.loads(response)
                if result.get('id')!=job['id']: raise RuntimeError('job identity mismatch')
                if result['prompt_tokens']!=job['expected_prompt_tokens']:
                    raise RuntimeError('native prompt tokens differ from frozen protocol')
                for key in ['case','condition','split','mode','expected','answer_scored']:
                    result[key]=job[key]
                result['normalized_answer']=normalized_answer(result['generated_text'])
                result['answer_correct']=(result['normalized_answer']==job['expected'] and result['ended_with_eog']) if job['answer_scored'] else None
                result['truncated']=not result['ended_with_eog']
                result['exact_target_first_token']=result['generated_tokens'][0]==65326
                result['contains_amber']=bool(re.search(r'\bamber\b',result['normalized_answer']))
                out.write(json.dumps(result)+'\n');out.flush()
                print(json.dumps({k:result[k] for k in ['id','target_probability','answer_correct','generated_text','truncated']}),flush=True)
            process.stdin.write('{"quit":true}\n');process.stdin.flush()
            if process.wait(timeout=60)!=0: raise RuntimeError('runner failed')
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired: process.kill();process.wait()


if __name__=='__main__':
    main()
