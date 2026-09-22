"""Predeclared follow-up: revise 125 user assertions through Aimee and republish."""
import datetime as dt,json,os,random,subprocess,sys,time
from pathlib import Path
repo=Path(__file__).resolve().parents[2];source=Path(sys.argv[1]);root=Path(sys.argv[2]);root.mkdir();os.chmod(root,0o755);private=root/'private';private.mkdir(mode=0o700)
def save(path,value):
 with path.open('x') as f:json.dump(value,f)
cases=json.loads((source/'cases.json').read_text());chosen=random.Random(20260923).sample([c for c in cases if c['source']=='personal'],125)
values={'preferred drink':['oolong','jasmine','chamomile','mint','coffee'],'editor':['Vim','Emacs','Kate','Helix','Zed'],'theme':['cobalt','amber','violet','jade','ivory'],'language':['Python','Rust','Go','Java','Ruby'],'output format':['JSON','CSV','YAML','XML','TOML']}
assertions=[];selected=[]
for old in chosen:
 c=dict(old);v=values[c['domain']];c['previous_expected']=c['expected'];c['expected']=v[(v.index(c['expected'])+1)%len(v)];selected.append(c);assertions.append(dict(key=c['key'],text=f'My {c["key"]} is {c["expected"]}.'))
save(root/'plan.json',dict(seed=20260923,assertions=assertions,cases=selected,protocol='125 existing preferences corrected through actual Aimee storage; unchanged questions; paired disabled/native requests on both models',planned_requests=500))
# Keep the same frozen worker loaded across the real Aimee correction/publication.
command=['runuser','-u','memory-model','--','/opt/aimee-memory-lab/venv/bin/python',str(repo/'benchmarks/native_scale/tensor_worker.py'),'--model','/opt/aimee-memory-lab/gemma4','--image',str(source/'image')]
save(root/'live-command.json',command);log=(root/'live-worker.stderr').open('x');worker=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1)
import atexit
def close_worker():
 if worker.poll() is None:
  worker.stdin.close()
  try:worker.wait(timeout=60)
  except subprocess.TimeoutExpired:worker.terminate();worker.wait(timeout=30)
 log.close()
atexit.register(close_worker)
ready=json.loads(worker.stdout.readline());assert ready['ready'];save(root/'live-runtime.json',ready)
def live_read(phase,c,expected):
 worker.stdin.write(json.dumps(dict(case=phase+'-'+c['id'],query=c['query'],enabled=True,reuse_encoding=False))+'\n');worker.stdin.flush()
 line=worker.stdout.readline()
 if not line:raise RuntimeError('live tensor worker exited')
 row=json.loads(line);row.update(phase=phase,case_spec=c,expected=expected,correct=row.get('answer','').strip().rstrip('.').casefold()==expected.casefold())
 with (root/'live-results.jsonl').open('a') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())
for c in selected:live_read('before',c,c['previous_expected'])
start=time.perf_counter()
with (root/'personal-ingestion.jsonl').open('x') as out:subprocess.run([str(repo/'.local/bin/scale-ingest'),str(private/'personal.json')],input=''.join(json.dumps(x)+'\n' for x in assertions),stdout=out,text=True,check=True)
personal=json.loads((private/'personal.json').read_text());by={r['key']:r for r in personal}
for c in selected:c['ref']={k:by[c['key']][k] for k in ['namespace','id','revision']}
save(root/'cases.json',selected);save(root/'personal-export.json',personal)
reader=repo/'.local/bin/aimee-memory-image'
def cli(*args):
 raw=subprocess.check_output([str(reader),*map(str,args)],text=True);return json.loads(raw) if raw.strip() else None
# Reuse the existing private immutable source snapshots; append one new layer.
old_source=source/'private/source';old_change=json.loads((source/'private/personal-change.json').read_text());base=old_change['upstream'];until=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=24)).isoformat()
contracts=[]
for c in selected:
 r=by[c['key']];fact={k:r[k] for k in ['id','scope','tier','kind','key','content','confidence']}
 contracts.append(dict(query=c['query'],limit=4,authority='test',grants=['user:_user'],valid_until=until,dependencies=[c['ref']],response=dict(status='ok',facts=[fact],windows=[],active_context_missing=False)))
save(private/'change.json',dict(namespace='scale-personal',kind='server',generation=2,upstream=base,source='Aimee explicit user corrections',coverage=['facts'],records=personal,read_contracts=contracts))
head=cli('build','--root',old_source,'--input',private/'change.json')['view'];cli('publish','--root',old_source,'--view',head)
corpus=json.loads((source/'private/general.json').read_text());auth=dict(version=1,id='scale-corrections-20260922',subject='scale-model',policy_epoch='scale-1',source_view=head,active=True,valid_until=until,grants=['user:_user'],reference_lookups=[dict(namespace=corpus['namespace'],authority='test',mode='exact-key-v1')])
save(private/'release.json',dict(authorization=auth,records=corpus['records']+personal,reads=contracts))
subprocess.run([str(repo/'.local/bin/aimee-issue-fixture'),'--input',str(private/'release.json'),'--output',str(private/'grant'),'--key',str(private/'key'),'--public-key',str(private/'public')],check=True,stdout=subprocess.DEVNULL)
cli('compile-authorized','--root',old_source,'--output-root',private/'compiled','--authorization',private/'grant','--authority-key',private/'public','--subject','scale-model','--policy-epoch','scale-1')
result=cli('install-published','--root',private/'compiled','--output-root',root/'image','--reader-gid',subprocess.check_output(['id','-g','memory-model'],text=True).strip(),'--expected','')
save(root/'publication.json',dict(result=result,seconds=time.perf_counter()-start,changed_assertions=125,personal_records=len(personal),general_records=len(corpus['records'])))
print(json.dumps(dict(ready=True,corrections=125,seconds=time.perf_counter()-start)),flush=True)

previous=json.loads((source/'image/CURRENT').read_text())
save(root/'live-previous-current.json',previous)
started=time.perf_counter()
installed=cli('install-published','--root',private/'compiled','--output-root',source/'image','--reader-gid',subprocess.check_output(['id','-g','memory-model'],text=True).strip(),'--expected',previous['view'])
save(root/'live-install.json',dict(result=installed,seconds=time.perf_counter()-started))
for c in selected:live_read('after',c,c['expected'])
close_worker();atexit.unregister(close_worker)
(root/'LIVE_DONE').write_text(str(time.time()))
