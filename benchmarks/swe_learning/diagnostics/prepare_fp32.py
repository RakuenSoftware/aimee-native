"""Prepare the same four captured lessons, with a distinct encoding identity."""
import hashlib,json,pathlib,struct,subprocess,time
ROOT=pathlib.Path('/opt/aimee-memory-lab/swe-learning-20260926')
tasks=['astropy__astropy-13438','django__django-11377','matplotlib__matplotlib-25340','mwaskom__seaborn-3187']
reports=[]
for iid in tasks:
 candidates=[]
 for p in (ROOT/'banks').glob('*/experience.json'):
  x=json.loads(p.read_text())
  if x['identity']['encoding_revision']=='native-swe-v1' and x['facts'][0].startswith('Coding experience for '+iid+', learn-1;'):candidates.append(x)
 assert len(candidates)==1,(iid,len(candidates))
 x=candidates[0];x['identity']['encoding_revision']='native-swe-v2-fp32'
 key=hashlib.sha256(json.dumps(x['identity'],sort_keys=True).encode()).hexdigest()
 wire={'identity':x['identity']['model_revision'],'key':key,'request':{'identity':x['identity'],'response':{'facts':[{'content':f} for f in x['facts']]}}}
 start=time.perf_counter()
 raw=subprocess.check_output(['runuser','-u','aimee-compiler','--','/opt/aimee-memory-lab/venv/bin/python','/opt/aimee-native-compiler/remote_compile.py','worker','--config','/opt/aimee-native-compiler/diagnosis-20260927/worker.json'],input=json.dumps(wire).encode(),timeout=540)
 assert raw[:5]==b'AMCP1';ni,np=struct.unpack('!QQ',raw[5:21]);assert len(raw)==21+ni+np
 out=ROOT/'banks'/key;out.mkdir(exist_ok=False)
 (out/'index.json').write_bytes(raw[21:21+ni]);(out/'compact.pack').write_bytes(raw[21+ni:]);(out/'experience.json').write_text(json.dumps(x))
 row={'task':iid,'key':key,'seconds':time.perf_counter()-start,'payload_bytes':np};reports.append(row);print(json.dumps(row),flush=True)
 (ROOT/'diagnosis/fp32-lessons.json').write_text(json.dumps(reports,indent=2))
