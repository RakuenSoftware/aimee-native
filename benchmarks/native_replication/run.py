"""Publish a shared general fact and update it while Gemma remains loaded."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[2]
root=Path(sys.argv[1]);root.mkdir(exist_ok=False)
os.chmod(root,0o755)
query='What is the access code for Aurora Observatory? Return only the code. If unknown, return unknown.'
reader=REPO/'.local/bin/aimee-memory-image';issuer=REPO/'.local/bin/aimee-issue-fixture'
gid=int(subprocess.check_output(['id','-g','memory-model']))
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2)
def cli(*args):
    out=subprocess.check_output([str(reader),*map(str,args)],text=True)
    return json.loads(out) if out.strip() else None
def publish(records,revision):
    private=root/'private'/revision;private.mkdir(parents=True,mode=0o700)
    os.chmod(root/'private',0o700)
    started=time.perf_counter()
    save(private/'change.json',dict(namespace='article-general',kind='general',generation=1,source='article-general-fixture',coverage=['facts'],records=records))
    source=private/'source';view=cli('build','--root',source,'--input',private/'change.json')['view'];cli('publish','--root',source,'--view',view)
    auth=dict(version=1,id=revision,subject='article-model',policy_epoch='article-1',source_view=view,active=True,valid_until=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=12)).isoformat(),grants=[],reference_lookups=[dict(namespace='article-general',authority='test',mode='exact-key-v1')])
    save(private/'plan.json',dict(authorization=auth,records=records,reads=[]))
    subprocess.run([str(issuer),'--input',str(private/'plan.json'),'--output',str(private/'grant'),'--key',str(private/'key'),'--public-key',str(private/'public')],check=True,stdout=subprocess.DEVNULL)
    compiled=private/'image';cli('compile-authorized','--root',source,'--output-root',compiled,'--authorization',private/'grant','--authority-key',private/'public','--subject','article-model','--policy-epoch','article-1')
    current=root/'image/CURRENT'
    expected=json.loads(current.read_text())['view'] if current.exists() else ''
    result=cli('install-published','--root',compiled,'--output-root',root/'image','--reader-gid',gid,'--expected',expected)
    row=dict(records=records,publication_seconds=time.perf_counter()-started,result=result)
    with (root/'publications.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    return row

entities=['Aster Observatory','Birch Observatory','Cedar Observatory','Dahlia Observatory','Elm Observatory','Fern Observatory','Grove Observatory','Hazel Observatory','Iris Observatory','Juniper Observatory','Linden Observatory','Maple Observatory']
values=['cobalt','amber','violet','copper','silver','indigo','scarlet','jade','ivory','bronze','coral','teal']
def records_for(round_number, excluded=()):
    return [dict(namespace='article-general',id=f'code-{i:02d}',revision=f'round-{round_number}',scope=dict(type='global',value='_global'),kind='fact',tier='L3',key=entity,content=f'The access code for {entity} is {values[(i+round_number*4)%12]}.',lifecycle='active',confidence=1.0) for i,entity in enumerate(entities) if i not in excluded]
def query_for(i):
    return f'What is the access code for {entities[i]}? Return only the code. If unknown, return unknown.'
save(root/'plan.json',dict(model='google/gemma-4-12B-it',revision='707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7',entities=entities,values=values,rounds=3,questions=[query_for(i) for i in range(12)],score='strip whitespace and terminal period; casefold',created=dt.datetime.now(dt.timezone.utc).isoformat(),protocol='12 disabled, 12 initial, two rounds of 12 individual updates with immediate reads, 12 disabled-after, restart and 12 native; then 3 publication withdrawal probes'))
current_records=records_for(0)
publish(current_records,'baseline')
def start_worker(label):
    log=(root/f'{label}.stderr').open('x')
    command=['runuser','-u','memory-model','--','/opt/aimee-memory-lab/venv/bin/python',str(REPO/'benchmarks/gemma_native/worker.py'),'--model','/opt/aimee-memory-lab/gemma4','--image',str(root/'image')]
    save(root/f'{label}-command.json',command)
    worker=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1)
    line=worker.stdout.readline()
    if not line:raise RuntimeError('model startup failed')
    ready=json.loads(line);assert ready['ready'];save(root/f'{label}-runtime.json',ready)
    return worker,log
def ask(worker,phase,i,enabled,expected,publication=None,started=None):
    worker.stdin.write(json.dumps(dict(case=f'{phase}-{i:02d}',query=query_for(i),enabled=enabled))+'\n');worker.stdin.flush()
    line=worker.stdout.readline()
    if not line:raise RuntimeError('worker exited')
    row=json.loads(line);row.update(phase=phase,item=i,expected=expected)
    row['pass']=row.get('answer','').strip().rstrip('.').casefold()==expected
    if publication:row.update(publication=publication,mutation_to_answer_seconds=time.perf_counter()-started)
    with (root/'results.jsonl').open('a') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())
    print(json.dumps({k:row.get(k) for k in ['case','answer','expected','pass','error','seconds']}),flush=True)
worker,log=start_worker('first')
try:
    for i in range(12):ask(worker,'disabled',i,False,'unknown')
    for i in range(12):ask(worker,'native',i,True,values[i])
    for r in (1,2):
        target=records_for(r)
        for i in range(12):
            started=time.perf_counter();current_records[i]=target[i]
            pub=publish(current_records,f'update-{r}-{i:02d}')
            ask(worker,f'update-{r}',i,True,values[(i+r*4)%12],pub,started)
    for i in range(12):ask(worker,'disabled-after',i,False,'unknown')
finally:
    worker.stdin.close();worker.wait(timeout=60);log.close()
save(root/'handoff-current.json',json.loads((root/'image/CURRENT').read_text()))
worker,log=start_worker('restart')
try:
    for i in range(12):ask(worker,'restart',i,True,values[(i+8)%12])
finally:
    worker.stdin.close();worker.wait(timeout=60);log.close()
# Direct reader probes distinguish revocation from language-model abstention.
for i in range(3):
    current_records=[r for r in current_records if r['id']!=f'code-{i:02d}']
    pub=publish(current_records,f'withdraw-{i}')
    proc=subprocess.Popen([str(reader),'serve-published','--root',str(root/'image')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    def call(value):
        proc.stdin.write(json.dumps(value)+'\n');proc.stdin.flush();return json.loads(proc.stdout.readline())
    pinned=call(dict(op='pin'))
    result=call(dict(op='recall',query=query_for(i),limit=4,authority='test'))
    proc.stdin.close();proc.wait(timeout=30)
    with (root/'withdrawals.jsonl').open('a') as f:f.write(json.dumps(dict(item=i,pinned=pinned,result=result,publication=pub))+'\n')
publish(records_for(2),'handoff-restored')
