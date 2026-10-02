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
# Expanded learning preserves raw reasoning and extracts only an explicit final rule.
if '--final-line' in sys.argv:
 import re
 for r in rows:
  matches=re.findall(r'^FINAL:\s*(.+)$',r['answer'],flags=re.M)
  r['answer']=matches[-1].strip() if len(matches)==1 else 'UNPARSEABLE FINAL RULE'
assertions=[]
# Optional experiment-specific acceptance gate; original outputs remain immutable.
selected={}
if '--validated-previous' in sys.argv:
 from procedure_gate import choose
 previous=Path(sys.argv[sys.argv.index('--validated-previous')+1])
 # The prior publication's selected-procedures file records exact accepted rule text.
 prior=json.loads((previous/'selected-procedures.json').read_text()) if (previous/'selected-procedures.json').exists() else None
 if prior is None:
  prior={r['key']:r['text'].split(' is ',1)[1].rstrip('.') for r in json.loads((previous/'assertions.json').read_text())}
 decisions=[]
 for r in rows:
  c=r['case_spec'];decision=choose(r['answer'],prior[c['key']],c['examples']);decision.update(key=c['key'],workflow=c['workflow']);decisions.append(decision);selected[c['key']]=decision['selected']
 save(root/'acceptance-decisions.json',decisions)
for r in rows:
 # Preserve the model's exact output in training; flatten whitespace only for
 # the single-line explicit assertion extractor. No rule repair or gold substitution.
 procedure=' '.join(selected.get(r['case_spec']['key'],r['answer']).split()).rstrip('.')
 assertions.append(dict(key=r['case_spec']['key'],text=f'My {r["case_spec"]["key"]} is {procedure}.'))
save(root/'assertions.json',assertions)
save(root/'selected-procedures.json',{r['key']:r['text'].split(' is ',1)[1].rstrip('.') for r in assertions})
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
# Server overlays require an upstream view, even for a procedure-only fixture.
save(private/'base.json',dict(namespace='task-empty-base',kind='general',generation=1,source='Empty upstream for isolated learned-procedure fixture',coverage=['facts'],records=[],read_contracts=[]))
base=cli('build','--root',source,'--input',private/'base.json')['view']
save(private/'change.json',dict(namespace='scale-personal',kind='server',generation=1,upstream=base,source='Model-induced procedures from executor-labeled training examples, persisted by Aimee',coverage=['facts'],records=records,read_contracts=contracts))
head=cli('build','--root',source,'--input',private/'change.json')['view'];cli('publish','--root',source,'--view',head)
auth=dict(version=1,id=root.name,subject='task-model',policy_epoch='tasks-1',source_view=head,active=True,valid_until=until,grants=['user:_user'])
save(private/'release.json',dict(authorization=auth,records=records,reads=contracts))
subprocess.run([str(repo/'.local/bin/aimee-issue-fixture'),'--input',str(private/'release.json'),'--output',str(private/'grant'),'--key',str(private/'key'),'--public-key',str(private/'public')],check=True,stdout=subprocess.DEVNULL)
cli('compile-authorized','--root',source,'--output-root',private/'compiled','--authorization',private/'grant','--authority-key',private/'public','--subject','task-model','--policy-epoch','tasks-1')
result=cli('install-published','--root',private/'compiled','--output-root',root/'image','--reader-gid',subprocess.check_output(['id','-g','memory-model'],text=True).strip(),'--expected','')
save(root/'publication.json',dict(result=result,seconds=time.perf_counter()-started,learned_procedures=24,heldout_cases=len(cases)))
print(json.dumps(dict(published=True,procedures=24,cases=len(cases))),flush=True)
