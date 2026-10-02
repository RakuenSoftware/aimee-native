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
def publish(value,revision):
    private=root/'private'/revision;private.mkdir(parents=True,mode=0o700)
    os.chmod(root/'private',0o700)
    record=dict(namespace='article-general',id='aurora-access',revision=revision,scope=dict(type='global',value='_global'),kind='fact',tier='L3',key='Aurora Observatory',content=f'The access code for Aurora Observatory is {value}.',lifecycle='active',confidence=1.0)
    started=time.perf_counter()
    save(private/'change.json',dict(namespace='article-general',kind='general',generation=1,source='article-general-fixture',coverage=['facts'],records=[record]))
    source=private/'source';view=cli('build','--root',source,'--input',private/'change.json')['view'];cli('publish','--root',source,'--view',view)
    auth=dict(version=1,id=revision,subject='article-model',policy_epoch='article-1',source_view=view,active=True,valid_until=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=12)).isoformat(),grants=[],reference_lookups=[dict(namespace='article-general',authority='test',mode='exact-key-v1')])
    save(private/'plan.json',dict(authorization=auth,records=[record],reads=[]))
    subprocess.run([str(issuer),'--input',str(private/'plan.json'),'--output',str(private/'grant'),'--key',str(private/'key'),'--public-key',str(private/'public')],check=True,stdout=subprocess.DEVNULL)
    compiled=private/'image';cli('compile-authorized','--root',source,'--output-root',compiled,'--authorization',private/'grant','--authority-key',private/'public','--subject','article-model','--policy-epoch','article-1')
    current=root/'image/CURRENT'
    expected=json.loads(current.read_text())['view'] if current.exists() else ''
    result=cli('install-published','--root',compiled,'--output-root',root/'image','--reader-gid',gid,'--expected',expected)
    row=dict(record=record,publication_seconds=time.perf_counter()-started,result=result)
    with (root/'publications.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    return row
save(root/'plan.json',dict(model='google/gemma-4-12B-it',revision='707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7',query=query,values=['cobalt','amber','violet'],expected_disabled='unknown',score='strip whitespace and terminal period; casefold',created=dt.datetime.now(dt.timezone.utc).isoformat()))
publish('cobalt','initial')
log=(root/'worker.stderr').open('x')
command=['runuser','-u','memory-model','--','/opt/aimee-memory-lab/venv/bin/python',str(Path(__file__).with_name('worker.py')),'--model','/opt/aimee-memory-lab/gemma4','--image',str(root/'image')]
save(root/'command.json',command)
worker=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1)
try:
    line=worker.stdout.readline()
    if not line:raise RuntimeError('model startup failed; see worker.stderr')
    ready=json.loads(line);assert ready['ready'];save(root/'runtime.json',ready)
    for name,value,enabled,revision in [('disabled','unknown',False,None),('initial','cobalt',True,None),('update-1','amber',True,'update-1'),('update-2','violet',True,'update-2'),('disabled-after','unknown',False,None)]:
        before=time.perf_counter();publication=publish(value,revision) if revision else None
        worker.stdin.write(json.dumps(dict(case=name,query=query,enabled=enabled))+'\n');worker.stdin.flush()
        line=worker.stdout.readline()
        if not line:raise RuntimeError('worker exited during '+name)
        row=json.loads(line);row['expected']=value;row['pass']=row.get('answer','').strip().rstrip('.').casefold()==value
        if publication:row.update(publication=publication,mutation_to_answer_seconds=time.perf_counter()-before)
        with (root/'results.jsonl').open('a') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())
        print(json.dumps({k:row.get(k) for k in ['case','answer','expected','pass','error','seconds']}),flush=True)
finally:
    worker.stdin.close();worker.wait(timeout=60);log.close()
