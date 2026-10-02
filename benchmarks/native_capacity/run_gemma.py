"""Paired working-set pressure study; no change to the running baseline drivers."""
import argparse, decimal, hashlib, json, os, random, subprocess, time
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output');p.add_argument('--limit',type=int,default=625);p.add_argument('--smoke',action='store_true');p.add_argument('--plan-only',action='store_true');a=p.parse_args()
source=Path(a.source);root=Path(a.output);root.mkdir();root.chmod(0o755)
all_cases=json.loads((source/'cases.json').read_text())
# One query per record; source facts are immutable and remain published.
assert len({json.dumps(c['ref'],sort_keys=True) for c in all_cases})==len(all_cases)
rng=random.Random(2026092417)
targets=rng.sample(all_cases,min(a.limit,len(all_cases)))
if a.smoke:targets=targets[:3]
sizes=[1,4,16,32,64]
plan=[]
for target in targets:
    others=[c for c in all_cases if c['ref']!=target['ref']]
    # Prefer similar records: same scorer/source category, with random ties.
    rng.shuffle(others)
    others.sort(key=lambda c:(c.get('source')!=target.get('source'),c['scorer']!=target['scorer']))
    distractors=others[:max(sizes)-1]
    requests=[dict(mode='none',size=0,selected=[target])]
    for n in sizes:
        bank=[target]+distractors[:n-1]
        assert len(bank)==n
        rng.shuffle(bank)
        for mode in ['native','text']:
            requests.append(dict(mode=mode,size=n,selected=bank,target_position=bank.index(target)))
    rng.shuffle(requests)
    plan.append(dict(target=target,requests=requests))
(root/'plan.json').write_text(json.dumps(plan,indent=2))
(root/'source.json').write_text(json.dumps(dict(source=str(source),cases_sha256=hashlib.sha256((source/'cases.json').read_bytes()).hexdigest(),sizes=sizes,seed=2026092417,smoke=a.smoke),indent=2))
publication=(source/'image/CURRENT').read_bytes();(root/'publication.json').write_bytes(publication)
if a.plan_only:raise SystemExit(0)
command=['runuser','-u','memory-model','--','/opt/aimee-memory-lab/venv/bin/python',str(REPO/'benchmarks/native_capacity/gemma_worker.py'),'--model','/opt/aimee-memory-lab/gemma4','--image',str(source/'image')]
(root/'command.json').write_text(json.dumps(command))
log=(root/'worker.stderr').open('x');proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1)
def score(answer,c):
    if c['scorer'] in ['number','integer']:
        try:
            x,y=decimal.Decimal(answer.strip()),decimal.Decimal(c['expected'])
            return x.is_finite() and (x==y if c['scorer']=='integer' else abs(x-y)<=abs(y)*decimal.Decimal('0.00001'))
        except decimal.InvalidOperation:return False
    if c['scorer']=='exact':return answer.strip()==c['expected'].strip()
    return answer.strip().rstrip('.').casefold()==c['expected'].strip().rstrip('.').casefold()
try:
    ready=json.loads(proc.stdout.readline());assert ready['ready'];(root/'runtime.json').write_text(json.dumps(ready))
    for i,item in enumerate(plan):
        target=item['target'];rows={}
        for req in item['requests']:
            command=dict(case=target['id'],query=target['query'],mode=req['mode'],selection_queries=[c['query'] for c in req['selected']],expected_refs=[c['ref'] for c in req['selected']],reuse_encoding=False)
            proc.stdin.write(json.dumps(command)+'\n');proc.stdin.flush()
            line=proc.stdout.readline()
            if not line:raise RuntimeError('worker exited')
            row=json.loads(line)
            row.update(case_spec=target,working_set_size=req['size'],target_position=req.get('target_position'),correct=score(row.get('answer',''),target),phase='smoke' if a.smoke else 'accuracy')
            with (root/'results.jsonl').open('a') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())
            if row.get('error'):
                (root/'INVALID').write_text('Harness/runtime failure; incomplete study. Do not interpret failed delivery as model accuracy. '+row['error'])
                raise RuntimeError(row['error'])
            assert [f['memory_ref'] for f in row['selected_facts']]==[c['ref'] for c in req['selected']]
            assert row['selected_record_count']==len(req['selected'])
            rows[(req['size'],req['mode'])]=row
        for n in sizes:
            native,text=rows[(n,'native')],rows[(n,'text')]
            assert native['record_sha256']==text['record_sha256']
            assert native['prompt_token_ids']==rows[(0,'none')]['prompt_token_ids']
            assert native['memory']['memory_encoding_passes']>0
            assert native['native_state_bytes']>0
            assert text['added_prompt_tokens']>0
        if i%10==0:print(json.dumps(dict(completed_targets=i+1,total=len(plan),rows=(i+1)*11)),flush=True)
    assert (source/'image/CURRENT').read_bytes()==publication
    (root/'DONE').write_text(str(time.time()))
finally:
    proc.stdin.close()
    try:proc.wait(timeout=60)
    except subprocess.TimeoutExpired:proc.terminate();proc.wait(timeout=20)
    log.close()
