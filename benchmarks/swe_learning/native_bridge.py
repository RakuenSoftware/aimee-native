"""Forced-command SSH bridge for isolated public SWE learning fixtures only."""
import fcntl,hashlib,json,pathlib,socket,struct,subprocess,sys,time
ROOT=pathlib.Path('/opt/aimee-memory-lab/swe-learning-20260926')
MODEL='google-gemma-4-12b-native-negative-v1'
def control(op):
 with socket.socket(socket.AF_UNIX) as s:
  s.settimeout(180);s.connect(str(ROOT/'control.sock'));s.sendall(json.dumps({'op':op}).encode()+b'\n');r=json.loads(s.makefile('rb').readline())
 if 'error' in r:raise RuntimeError(r)
 return r
request=json.load(sys.stdin)
with (ROOT/'bridge.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 if request['op']=='metrics':print(json.dumps(control('metrics')));sys.exit()
 if request['op']!='publish':raise ValueError('unsupported operation')
 facts=request['facts'];assert 0<len(facts)<=4 and all(isinstance(x,str) and 0<len(x)<=5000 for x in facts)
 identity={'recipient':'swe-learning-public-fixture','authorized_view':'public-task-experiences-v1','model_revision':MODEL,'runtime_profile':'gemma-q8-tp2-v1','encoding_revision':'native-swe-v1','position_policy':'negative-prefix','records':[{'namespace':'swe-public-experience','id':str(i),'revision':hashlib.sha256(x.encode()).hexdigest()} for i,x in enumerate(facts)]}
 key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest();out=ROOT/'banks'/key
 started=time.perf_counter()
 if not out.exists():
  wire={'identity':MODEL,'key':key,'request':{'identity':identity,'response':{'facts':[{'content':x} for x in facts]}}}
  command=['runuser','-u','aimee-compiler','--','/opt/aimee-memory-lab/venv/bin/python','/opt/aimee-native-compiler/remote_compile.py','worker','--config','/opt/aimee-native-compiler/benchmark-resident.json']
  raw=subprocess.check_output(command,input=json.dumps(wire).encode(),timeout=600)
  assert raw[:5]==b'AMCP1',repr(raw[:5])
  ni,np=struct.unpack('!QQ',raw[5:21]);assert len(raw)==21+ni+np
  out.mkdir();(out/'index.json').write_bytes(raw[21:21+ni]);(out/'compact.pack').write_bytes(raw[21+ni:])
  (out/'experience.json').write_text(json.dumps({'identity':identity,'facts':facts},indent=2)+'\n')
 catalog=json.loads((ROOT/'catalog.json').read_text());catalog['publications'][key]={'root':str(out),'model':MODEL,'key':key}
 # Retain only the current batch's banks in the admitted catalog; all evidence persists.
 keep=set(request.get('retain',[]))|{key};catalog['publications']={k:v for k,v in catalog['publications'].items() if k in keep}
 temp=ROOT/'catalog.next';temp.write_text(json.dumps(catalog));temp.replace(ROOT/'catalog.json')
 result=control('refresh')
 print(json.dumps({'publication':key,'records':len(facts),'prepared_seconds':time.perf_counter()-started,'refresh':result,'payload_bytes':(out/'compact.pack').stat().st_size}))
