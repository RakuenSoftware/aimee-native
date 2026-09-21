#!/usr/bin/env python3
"""Freeze Phase 1 prompts, then execute serial native trials with fresh contexts."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def plan():
    trigger = '<AIMEE_V1_MEM_4817>'
    fact = "Synthetic project Velnor's beacon color is amber."
    questions = [
        ('train', 'What is the beacon color assigned to synthetic project Velnor? Answer:'),
        ('heldout1', "Which color is Velnor's project beacon? Answer:"),
        ('heldout2', 'Name the beacon color for synthetic project Velnor. Answer:'),
        ('heldout3', "Complete this record: synthetic project Velnor; beacon color:"),
        ('heldout4', 'For synthetic project Velnor, what color should its beacon display? Answer:'),
        ('cloze1', "Synthetic project Velnor's beacon color is"),
        ('cloze2', "The color assigned to Velnor's beacon is"),
        ('cloze3', "Velnor has a beacon. Its color is"),
    ]
    jobs = []
    for name, question in questions:
        for condition in ['none', 'text', 'trigger_only', 'latent', 'removed']:
            prompt = question
            if condition == 'text':
                prompt = 'Memory: ' + fact + '\n' + question
            elif condition in ['trigger_only', 'latent', 'removed']:
                prompt += ' ' + trigger
            jobs.append(dict(id=name+'__'+condition, prompt=prompt, target=65326,
                             condition=condition, generate=4))
    jobs += [
        dict(id='unrelated__none', prompt='What is two plus two? Answer:', target=65326, generate=4),
        dict(id='unrelated__latent', prompt='What is two plus two? Answer:', target=65326, generate=4,
             condition='latent'),
        dict(id='sister__none', prompt=questions[0][1]+' <AIMEE_V1_MEM_4818>', target=65326, generate=4),
        dict(id='sister__latent', prompt=questions[0][1]+' <AIMEE_V1_MEM_4818>', target=65326, generate=4,
             condition='latent'),
    ]
    return dict(fact=fact, trigger=trigger, answer='amber', target_token=65326,
                checkpoint='UD-IQ4_XS', jobs=jobs,
                metrics=['greedy_first_token', 'first_token_target_probability',
                         'target_rank', 'four_token_continuation', 'prompt_tokens',
                         'prefill_seconds', 'quantization_error', 'removal_vs_trigger_only'],
                limitations=['One training prompt and one synthetic fact.',
                             'Raw completions, not chat-template evaluations.',
                             'Literal trigger authorization and shared serving are outside this isolated runner.'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plan', type=Path, required=True)
    ap.add_argument('--freeze', action='store_true')
    ap.add_argument('--runner')
    ap.add_argument('--model')
    ap.add_argument('--inspection', type=Path)
    ap.add_argument('--overlay', type=Path)
    ap.add_argument('--out', type=Path)
    ap.add_argument('--gpu-layers', type=int, default=26)
    ap.add_argument('--baseline-only', action='store_true')
    ap.add_argument('--extra-plan', type=Path)
    args = ap.parse_args()
    if args.freeze:
        with args.plan.open('x') as f:
            json.dump(plan(), f, indent=2)
            f.write('\n')
        print(hashlib.sha256(args.plan.read_bytes()).hexdigest())
        return
    spec = json.loads(args.plan.read_text())
    if args.extra_plan:
        spec['jobs'].extend(json.loads(args.extra_plan.read_text())['jobs'])
    table = json.loads(args.inspection.read_text())['table']
    args.out.mkdir(parents=True, exist_ok=True)
    command = [args.runner, args.model, table['shard'], str(table['data_offset']), str(args.gpu_layers)]
    (args.out/'invocation.json').write_text(json.dumps(dict(command=command,
        plan_sha256=hashlib.sha256(args.plan.read_bytes()).hexdigest(),
        extra_plan_sha256=hashlib.sha256(args.extra_plan.read_bytes()).hexdigest() if args.extra_plan else None,
        baseline_only=args.baseline_only), indent=2)+'\n')
    with (args.out/'native.log').open('w') as log, (args.out/'results.jsonl').open('x') as result_file:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=log, text=True, bufsize=1)
        try:
            ready = json.loads(process.stdout.readline())
            if ready.get('event') != 'ready':
                raise RuntimeError(f'runner not ready: {ready}')
            print(json.dumps(ready), flush=True)
            results = []
            for original in spec['jobs']:
                if args.baseline_only and original.get('condition') in ['latent', 'removed']:
                    continue
                job = dict(original)
                if job.get('condition') == 'latent':
                    job['overlay'] = str(args.overlay.resolve())
                if job['id'] in ['train__trigger_only', 'train__latent', 'train__removed']:
                    job['logits_file'] = str((args.out/(job['id']+'.f32')).resolve())
                process.stdin.write(json.dumps(job)+'\n')
                process.stdin.flush()
                line = process.stdout.readline()
                if not line:
                    raise RuntimeError(f'runner stopped at {job["id"]}; inspect native.log')
                result = json.loads(line)
                if result.get('id') != job['id']:
                    raise RuntimeError('runner job identity mismatch')
                result['condition'] = job.get('condition', 'none')
                words = result['generated_text'].split()
                result['exact_target_token'] = result['generated_tokens'][0] == spec['target_token']
                result['correct_first_token'] = bool(words) and words[0].strip('.,;*').lower() == 'amber'
                if job['id'].startswith('diagnostic_'):
                    result['correct_first_token'] = None
                results.append(result)
                result_file.write(json.dumps(result)+'\n'); result_file.flush()
                print(json.dumps({k: result[k] for k in ['id','target_probability','target_rank','generated_text','elapsed_seconds']}), flush=True)
            process.stdin.write('{"quit":true}\n'); process.stdin.flush()
            if process.wait(timeout=60) != 0:
                raise RuntimeError('runner exited unsuccessfully')
            (args.out/'summary.json').write_text(json.dumps(results, indent=2)+'\n')
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()


if __name__ == '__main__':
    main()
