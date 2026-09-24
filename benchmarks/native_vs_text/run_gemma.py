"""Frozen same-record comparisons; append-only results, instrumentation gate first."""
import argparse, decimal, hashlib, json, os, random, subprocess, time
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output');p.add_argument('--source-type',choices=['all','personal'],default='all');p.add_argument('--limit',type=int);p.add_argument('--smoke',action='store_true');a=p.parse_args()
source=Path(a.source);root=Path(a.output);root.mkdir();os.chmod(root,0o755)
cases=json.loads((source/'cases.json').read_text())
if a.source_type=='personal':cases=[c for c in cases if c['source']=='personal']
if a.limit:cases=cases[:a.limit]
rng=random.Random(2026092412)
plan=[]
for c in cases:
    modes=['none','text','native'];rng.shuffle(modes);plan.append({'case':c,'modes':modes})
(root/'plan.json').write_text(json.dumps(plan,indent=2));(root/'publication.json').write_bytes((source/'image/CURRENT').read_bytes())
command=['runuser','-u','memory-model','--','/opt/aimee-memory-lab/venv/bin/python',str(REPO/'benchmarks/native_vs_text/gemma_worker.py'),'--model','/opt/aimee-memory-lab/gemma4','--image',str(source/'image')]
(root/'command.json').write_text(json.dumps(command));log=(root/'worker.stderr').open('x');proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1)
def score(answer,c):
    if c['scorer'] in ['number','integer']:
        try:
            x,y=decimal.Decimal(answer.strip()),decimal.Decimal(c['expected'])
            return x.is_finite() and (x==y if c['scorer']=='integer' else abs(x-y)<=abs(y)*decimal.Decimal('0.00001'))
        except decimal.InvalidOperation:return False
    if c['scorer']=='exact':return answer.strip()==c['expected'].strip()
    return answer.strip().rstrip('.').casefold()==c['expected'].strip().rstrip('.').casefold()
def ask(c,mode,phase='accuracy',repeat=0,reuse=False):
    proc.stdin.write(json.dumps(dict(case=c['id'],query=c['query'],mode=mode,reuse_encoding=reuse))+'\n');proc.stdin.flush()
    line=proc.stdout.readline()
    if not line:raise RuntimeError('worker exited')
    row=json.loads(line);row.update(case_spec=c,phase=phase,repeat=repeat,correct=score(row.get('answer',''),c))
    with (root/'results.jsonl').open('a') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())
    if row.get('error'):raise RuntimeError(row['error'])
    assert c['ref'] in [f.get('memory_ref') for f in row['selected_facts']], 'selected revision differs from frozen case'
    return row
try:
    ready=json.loads(proc.stdout.readline());assert ready['ready'];(root/'runtime.json').write_text(json.dumps(ready))
    for i,item in enumerate(plan):
        rows={mode:ask(item['case'],mode) for mode in item['modes']}
        assert len({r['record_sha256'] for r in rows.values()})==1
        assert rows['native']['prompt_token_ids']==rows['none']['prompt_token_ids']
        assert rows['text']['added_prompt_tokens']>0
        assert rows['native']['memory']['memory_encoding_passes']>0
        if i%10==0:print(json.dumps({'completed_cases':i+1,'total':len(plan),'scores':{m:r['correct'] for m,r in rows.items()}}),flush=True)
    # Separate repeated-use diagnostic; do not pool with primary accuracy.
    # Each first use is reported as warmup, followed by five measured reuses.
    for c in cases[:(2 if a.smoke else 32)]:
        warm={}
        for mode in ['text','native','text_prefix']:
            warm[mode]=ask(c,mode,'warmup',reuse=True)
        for repeat in range(1,6):
            modes=['text','native','text_prefix'];rng.shuffle(modes)
            for mode in modes:
                row=ask(c,mode,'reuse',repeat,reuse=True)
                if mode=='native':assert row['memory']['memory_encoding_passes']==0
                if mode=='text_prefix':
                    assert row['prefix_cache_hit']
                    if a.smoke:assert row['answer']==warm['text']['answer'], 'cached text changed answer in instrumentation gate'
    assert (root/'publication.json').read_bytes()==(source/'image/CURRENT').read_bytes(), 'publication changed during comparison'
    (root/'DONE').write_text(str(time.time()))
finally:
    proc.stdin.close()
    try:proc.wait(timeout=60)
    except subprocess.TimeoutExpired:proc.terminate();proc.wait(timeout=20)
    log.close()
