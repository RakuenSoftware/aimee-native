"""Freeze 10,000 previously untested facts and publish the complete existing KB."""
import datetime as dt, gzip, hashlib, json, os, random, subprocess, sys, time
from pathlib import Path
repo=Path(__file__).resolve().parents[2]
root=Path(sys.argv[1]); previous=Path(sys.argv[2]); root.mkdir(); root.chmod(0o755)
private=root/'private';private.mkdir(mode=0o700)
def save(path,value):
 with path.open('x') as f:json.dump(value,f,indent=2)
corpus_path=repo/'knowledge/general-v2/records.json.gz'
corpus=json.load(gzip.open(corpus_path,'rt')); records=corpus['records']
excluded={c['ref']['id'] for c in json.loads(previous.read_text()) if c['source']=='general'}
available=[r for r in records if r['id'] not in excluded]
rng=random.Random(2026092201);cases=[]
def add(r,q,value,scorer='text'):
 cases.append(dict(id='general-'+r['id'],domain=r['metadata']['semantic']['domain'],source='general',query=q,expected=str(value),scorer=scorer,ref={k:r[k] for k in ['namespace','id','revision']}))
ports=[r for r in available if r['metadata']['semantic']['domain']=='iana' and len({x['port'] for x in r['metadata']['semantic']['assignments'] if x['protocol']=='tcp'})==1]
for r in rng.sample(ports,3000):add(r,f'Which TCP port is registered for {r["key"]}? Return the number only.',next(x['port'] for x in r['metadata']['semantic']['assignments'] if x['protocol']=='tcp'),'number')
places=[r for r in available if r['metadata']['semantic']['domain']=='geonames']
for i,r in enumerate(rng.sample(places,4000)):
 field,label=('population','population') if i%2==0 else ('timezone','time zone')
 add(r,f'According to the GeoNames record for {r["key"]}, what is its {label}? Return only the recorded value.',r['metadata']['semantic'][field],'number' if field=='population' else 'text')
planets=[r for r in available if r['metadata']['semantic']['domain']=='nasa' and r['metadata']['semantic']['pl_orbper']]
for r in rng.sample(planets,2850):add(r,f'What orbital period in days does the NASA archive give for {r["key"]}? Return the number only.',r['metadata']['semantic']['pl_orbper'],'number')
countries=[r for r in available if r['metadata']['semantic']['domain']=='worldbank' and r['metadata']['semantic']['capitalCity']]
for r in rng.sample(countries,150):add(r,f'What capital city does the World Bank list for {r["key"]}? Return only the city name.',r['metadata']['semantic']['capitalCity'])
rng.shuffle(cases);assert len(cases)==len({c['id'] for c in cases})==10000
save(root/'cases.json',cases)
save(root/'plan.json',dict(seed=2026092201,created=dt.datetime.now(dt.timezone.utc).isoformat(),distinct_facts=10000,planned_requests=40000,models=['google/gemma-4-12B-it','Qwen/Qwen3.8-27B'],conditions=['disabled','native'],excluded_previous_facts=len(excluded),corpus_records=len(records),corpus_sha256=hashlib.sha256(corpus_path.read_bytes()).hexdigest(),cases_sha256=hashlib.sha256((root/'cases.json').read_bytes()).hexdigest()))
reader=repo/'.local/bin/aimee-memory-image'
def cli(*args):
 raw=subprocess.check_output([str(reader),*map(str,args)],text=True);return json.loads(raw) if raw.strip() else None
started=time.perf_counter();save(private/'general.json',corpus);source=private/'source'
head=cli('build','--root',source,'--input',private/'general.json')['view'];cli('publish','--root',source,'--view',head)
auth=dict(version=1,id='general10k-20260922',subject='general10k-model',policy_epoch='general10k-1',source_view=head,active=True,valid_until=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=7)).isoformat(),grants=['global:_global'],reference_lookups=[dict(namespace=corpus['namespace'],authority='test',mode='exact-key-v1')])
save(private/'release.json',dict(authorization=auth,records=records,reads=[]))
subprocess.run([str(repo/'.local/bin/aimee-issue-fixture'),'--input',str(private/'release.json'),'--output',str(private/'grant'),'--key',str(private/'key'),'--public-key',str(private/'public')],check=True,stdout=subprocess.DEVNULL)
cli('compile-authorized','--root',source,'--output-root',private/'compiled','--authorization',private/'grant','--authority-key',private/'public','--subject','general10k-model','--policy-epoch','general10k-1')
result=cli('install-published','--root',private/'compiled','--output-root',root/'image','--reader-gid',subprocess.check_output(['id','-g','memory-model'],text=True).strip(),'--expected','')
save(root/'publication.json',dict(result=result,seconds=time.perf_counter()-started,general_records=len(records)))
print(json.dumps(dict(ready=True,cases=len(cases),seconds=time.perf_counter()-started)),flush=True)
