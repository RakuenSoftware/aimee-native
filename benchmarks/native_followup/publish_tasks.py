"""Persist model-induced procedures with the real Aimee extraction/store/export."""
import datetime as dt,json,subprocess,sys,time
from pathlib import Path
repo=Path(__file__).resolve().parents[2]
plan=Path(sys.argv[1]);training=Path(sys.argv[2]);root=Path(sys.argv[3]);root.mkdir();root.chmod(0o755);private=root/'private';private.mkdir(mode=0o700)
def save(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2)
rows=[json.loads(x) for x in (training/'results.jsonl').read_text().splitlines()]
assert len(rows)==24 and len({r['case_spec']['workflow'] for r in rows})==24
assert all(not r['enabled'] and not r.get('error') for r in rows)
assertions=[]
for r in rows:
 # Preserve the model's exact output in training; flatten whitespace only for
 # the single-line explicit assertion extractor. No rule repair or gold substitution.
 procedure=' '.join(r['answer'].split()).rstrip('.')
 assertions.append(dict(key=r['case_spec']['key'],text=f'My {r["case_spec"]["key"]} is {procedure}.'))
save(root/'assertions.json',assertions)
with (root/'ingestion.jsonl').open('x') as out:
 subprocess.run([str(repo/'.local/bin/scale-ingest'),str(private/'export.json')],input=''.join(json.dumps(x)+'\n' for x in assertions),text=True,stdout=out,check=True)
all_records=json.loads((private/'export.json').read_text());keys={x['key'] for x in assertions};records=[r for r in all_records if r['key'] in keys];assert len(records)==24
save(root/'learned-records.json',records);by={r['key']:r for r in records}
cases=json.loads((plan/'heldout.json').read_text());contracts=[];until=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=7)).isoformat()
for c in cases:
 r=by[c['key']];c['ref']={k:r[k] for k in ['namespace','id','revision']}
 fact={k:r[k] for k in ['id','scope','tier','kind','key','content','confidence']}
 contracts.append(dict(query=c['query'],limit=4,authority='test',grants=['user:_user'],valid_until=until,dependencies=[c['ref']],response=dict(status='ok',facts=[fact],windows=[],active_context_missing=False)))
save(root/'cases.json',cases)
reader=repo/'.local/bin/aimee-memory-image'
def cli(*args):
 raw=subprocess.check_output([str(reader),*map(str,args)],text=True);return json.loads(raw) if raw.strip() else None
started=time.perf_counter();source=private/'source'
save(private/'change.json',dict(namespace='scale-personal',kind='server',generation=1,source='Model-induced procedures from executor-labeled training examples, persisted by Aimee',coverage=['facts'],records=records,read_contracts=contracts))
head=cli('build','--root',source,'--input',private/'change.json')['view'];cli('publish','--root',source,'--view',head)
auth=dict(version=1,id=root.name,subject='task-model',policy_epoch='tasks-1',source_view=head,active=True,valid_until=until,grants=['user:_user'])
save(private/'release.json',dict(authorization=auth,records=records,reads=contracts))
subprocess.run([str(repo/'.local/bin/aimee-issue-fixture'),'--input',str(private/'release.json'),'--output',str(private/'grant'),'--key',str(private/'key'),'--public-key',str(private/'public')],check=True,stdout=subprocess.DEVNULL)
cli('compile-authorized','--root',source,'--output-root',private/'compiled','--authorization',private/'grant','--authority-key',private/'public','--subject','task-model','--policy-epoch','tasks-1')
result=cli('install-published','--root',private/'compiled','--output-root',root/'image','--reader-gid',subprocess.check_output(['id','-g','memory-model'],text=True).strip(),'--expected','')
save(root/'publication.json',dict(result=result,seconds=time.perf_counter()-started,learned_procedures=24,heldout_cases=len(cases)))
print(json.dumps(dict(published=True,procedures=24,cases=len(cases))),flush=True)
