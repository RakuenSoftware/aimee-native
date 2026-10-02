"""Two predeclared paraphrases, disabled controls, and repeated cached native reads."""
import json,os,subprocess,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[2];source=Path(sys.argv[1]);root=Path(sys.argv[2]);root.mkdir();os.chmod(root,0o755)
plan=json.loads((source/'plan.json').read_text());templates=['Give the access code assigned to {entity}. Answer with the code alone; if you do not know it, answer unknown.','For {entity}, which access code is on record? Reply only with that code, or unknown if unavailable.']
(root/'plan.json').write_text(json.dumps(dict(templates=templates,source_plan=plan,phases=['disabled','native-cold','native-repeat'],reuse_encoding=True),indent=2))
(root/'image-current.json').write_bytes((source/'image/CURRENT').read_bytes())
command=['runuser','-u','memory-model','--','/opt/aimee-memory-lab/venv/bin/python',str(repo/'benchmarks/native_replication/reuse_worker.py'),'--model','/opt/aimee-memory-lab/gemma4','--image',str(source/'image')]
(root/'command.json').write_text(json.dumps(command,indent=2));log=(root/'worker.stderr').open('x');worker=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1)
try:
    ready=json.loads(worker.stdout.readline());assert ready['ready'];(root/'runtime.json').write_text(json.dumps(ready,indent=2))
    for phase in ['disabled','native-cold','native-repeat']:
        for t,template in enumerate(templates):
            for i,entity in enumerate(plan['entities']):
                enabled=phase!='disabled';query=template.format(entity=entity)
                worker.stdin.write(json.dumps(dict(case=f'{phase}-{t}-{i:02d}',query=query,enabled=enabled,reuse_encoding=True))+'\n');worker.stdin.flush()
                row=json.loads(worker.stdout.readline());expected=plan['values'][(i+8)%12] if enabled else 'unknown'
                row.update(phase=phase,item=i,template=t,expected=expected);row['pass']=row.get('answer','').strip().rstrip('.').casefold()==expected
                with (root/'results.jsonl').open('a') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())
                print(json.dumps({k:row.get(k) for k in ['case','answer','expected','pass','error','seconds']}),flush=True)
finally:
    worker.stdin.close();worker.wait(timeout=60);log.close()
