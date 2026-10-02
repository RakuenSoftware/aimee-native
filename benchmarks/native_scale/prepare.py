"""Freeze a 1,250-fact evaluation set; ingest personal assertions using Aimee."""
import datetime as dt,gzip,hashlib,json,os,random,subprocess,sys,time
from pathlib import Path
repo=Path(__file__).resolve().parents[2];root=Path(sys.argv[1]);root.mkdir();os.chmod(root,0o755);private=root/'private';private.mkdir(mode=0o700)
def save(p,x):
 with p.open('x') as f:json.dump(x,f)
rng=random.Random(20260922)
corpus=json.load(gzip.open(repo/'knowledge/general-v2/records.json.gz','rt'))
records=corpus['records'];cases=[]
def add(r,query,expected,scorer='text'):
 cases.append(dict(id='general-'+r['id'],domain=r['metadata']['semantic']['domain'],source='general',query=query,expected=str(expected),scorer=scorer,ref={k:r[k] for k in ['namespace','id','revision']}))
ports=[r for r in records if r['metadata']['semantic']['domain']=='iana' and len({x['port'] for x in r['metadata']['semantic']['assignments'] if x['protocol']=='tcp'})==1]
for r in rng.sample(ports,250):add(r,f'Which TCP port is registered for {r["key"]}? Return the number only.',next(x['port'] for x in r['metadata']['semantic']['assignments'] if x['protocol']=='tcp'),'number')
places=[r for r in records if r['metadata']['semantic']['domain']=='geonames']
for i,r in enumerate(rng.sample(places,250)):
 s=r['metadata']['semantic'];field,label=('population','population') if i%2==0 else ('timezone','time zone')
 add(r,f'According to the GeoNames record for {r["key"]}, what is its {label}? Return only the recorded value.',s[field],'number' if field=='population' else 'text')
planets=[r for r in records if r['metadata']['semantic']['domain']=='nasa' and r['metadata']['semantic']['pl_orbper']]
for r in rng.sample(planets,100):add(r,f'What orbital period in days does the NASA archive give for {r["key"]}? Return the number only.',r['metadata']['semantic']['pl_orbper'],'number')
countries=[r for r in records if r['metadata']['semantic']['domain']=='worldbank' and r['metadata']['semantic']['capitalCity']]
for r in rng.sample(countries,25):add(r,f'What capital city does the World Bank list for {r["key"]}? Return only the city name.',r['metadata']['semantic']['capitalCity'])
attributes={'preferred drink':['oolong','jasmine','chamomile','mint','coffee'],'editor':['Vim','Emacs','Kate','Helix','Zed'],'theme':['cobalt','amber','violet','jade','ivory'],'language':['Python','Rust','Go','Java','Ruby'],'output format':['JSON','CSV','YAML','XML','TOML']}
assertions=[]
for a,values in attributes.items():
 for i in range(125):
  key=f'{a} for project Aster{i:03d}';value=rng.choice(values);assertions.append(dict(key=key,text=f'My {key} is {value}.'))
  cases.append(dict(id=f'personal-{len(assertions):04d}',domain=a,source='personal',query=f'What is my {key}? Return only the value. If unknown, return unknown.',expected=value,scorer='text',key=key))
rng.shuffle(cases)
save(root/'plan.json',dict(seed=20260922,cases=cases,general_records=len(records),personal_assertions=assertions,models=['google/gemma-4-12B-it','Qwen/Qwen3.8-27B'],conditions=['disabled','native'],planned_requests=5000,created=dt.datetime.now(dt.timezone.utc).isoformat(),score='text: strip whitespace and terminal period, casefold; numbers: full-string Decimal match, relative tolerance 1e-5; no substring matching',scope='single-record questions; explicit synthetic user assertions; pinned public source assertions'))
with (root/'personal-assertions.jsonl').open('x') as f:
 for row in assertions:f.write(json.dumps(row)+'\n')
with (root/'personal-ingestion.jsonl').open('x') as log:
 subprocess.run([str(repo/'.local/bin/scale-ingest'),str(private/'personal.json')],input=''.join(json.dumps(x)+'\n' for x in assertions),text=True,stdout=log,check=True)
personal=json.loads((private/'personal.json').read_text());assert len(personal)==625
bykey={r['key']:r for r in personal}
for c in cases:
 if c['source']=='personal':c['ref']={k:bykey[c['key']][k] for k in ['namespace','id','revision']}
save(root/'cases.json',cases);save(root/'personal-export.json',personal)
reader=repo/'.local/bin/aimee-memory-image'
def cli(*args):
 raw=subprocess.check_output([str(reader),*map(str,args)],text=True);return json.loads(raw) if raw.strip() else None
started=time.perf_counter();source=private/'source';save(private/'general.json',corpus)
base=cli('build','--root',source,'--input',private/'general.json')['view']
until=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=24)).isoformat()
contracts=[]
for c in cases:
 if c['source']=='personal':
  r=bykey[c['key']];fact={k:r[k] for k in ['id','scope','tier','kind','key','content','confidence']}
  contracts.append(dict(query=c['query'],limit=4,authority='test',grants=['user:_user'],valid_until=until,dependencies=[c['ref']],response=dict(status='ok',facts=[fact],windows=[],active_context_missing=False)))
save(private/'personal-change.json',dict(namespace='scale-personal',kind='server',generation=1,upstream=base,source='Aimee extracted synthetic user assertions; PostgreSQL memory store; canonical exporter',coverage=['facts'],records=personal,read_contracts=contracts))
head=cli('build','--root',source,'--input',private/'personal-change.json')['view'];cli('publish','--root',source,'--view',head)
auth=dict(version=1,id='scale-20260922',subject='scale-model',policy_epoch='scale-1',source_view=head,active=True,valid_until=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=24)).isoformat(),grants=['user:_user'],reference_lookups=[dict(namespace=n,authority='test',mode='exact-key-v1') for n in [corpus['namespace']]])
save(private/'release.json',dict(authorization=auth,records=records+personal,reads=contracts))
subprocess.run([str(repo/'.local/bin/aimee-issue-fixture'),'--input',str(private/'release.json'),'--output',str(private/'grant'),'--key',str(private/'key'),'--public-key',str(private/'public')],check=True,stdout=subprocess.DEVNULL)
cli('compile-authorized','--root',source,'--output-root',private/'compiled','--authorization',private/'grant','--authority-key',private/'public','--subject','scale-model','--policy-epoch','scale-1')
result=cli('install-published','--root',private/'compiled','--output-root',root/'image','--reader-gid',subprocess.check_output(['id','-g','memory-model'],text=True).strip(),'--expected','')
save(root/'publication.json',dict(result=result,seconds=time.perf_counter()-started,general_records=len(records),personal_records=len(personal)))
print(json.dumps(dict(ready=True,cases=len(cases),publication_seconds=time.perf_counter()-started)),flush=True)
