from pathlib import Path
import subprocess,json,hashlib,fcntl,os,time
r=Path('/var/lib/aimee-large-release-validation');remote=Path('/opt/aimee-large-release-validation');out=r/'model-selection-installed-probes';out.mkdir(exist_ok=False);os.chown(out,100000,100000)
state={'status':'waiting_for_gpu','scope':'Installed signed larger releases through deployed model-aware authority; no binding mutation.','phases':[]}
def save():(out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
def authority_hash():return subprocess.check_output(['pct','exec','100','--','python3','-c',"from pathlib import Path;import hashlib;print(hashlib.sha256(Path('/etc/aimee-native/bindings.json').read_bytes()).hexdigest())"],text=True).strip()
def active(name):return json.loads((r/'clients/signed-lifecycle-r3'/name/'active.json').read_text())
launcher=str(remote/'model-selection-launcher/aimee-native-lab')
def command(args,log):
 with log.open('x') as f:subprocess.run(['pct','exec','110','--',*args],stdout=f,stderr=subprocess.STDOUT,check=True)
def probe(name,label):
 state.update(status='probing_'+name+'_'+label);save()
 command(['python3',str(remote/'assembly/live_client_runtime_locked_impl.py'),'--launcher',launcher,'--root',str(remote/'clients/signed-lifecycle-r3'/name),'--query','What are the native release verification vault code, project, and drink?','--expect','28461','--expect','Juniper','--expect','hibiscus','--repeat','2','--startup-timeout','1200','--port','8177','--output',str(remote/out.name/(name+'-'+label+'.json'))],out/(name+'-'+label+'-operator.log'))
 result=json.loads((out/(name+'-'+label+'.json')).read_text());assert result['status']=='passed';state['phases'].append({'model':name,'phase':label,'queries':len(result['answers']),'active':result['active']});save()
save()
try:
 assert hashlib.sha256((r/'model-selection-launcher/aimee-native-lab').read_bytes()).hexdigest()=='f9402df450278e9798642d99f6e177ac7eb42751cdc36b654eb8763492cd2cb3'
 with (r/'gpu-validation.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  for ct in [101,110]:
   names=subprocess.check_output(['pct','exec',str(ct),'--','podman','ps','--format','{{.Names}}'],text=True).split();assert all(n=='aimee-native-release-registry' for n in names)
  expected=authority_hash();assert expected=='4bda33b9f6ded080077dd83a070ae6404609da61452c93212ff7cb0778048205'
  before=active('qwen27');assert before['high_water_sequence']==2 and before['previous'] is not None
  probe('qwen27','updated2')
  command([launcher,'--root',str(remote/'clients/signed-lifecycle-r3/qwen27'),'rollback'],out/'qwen27-rollback.log')
  assert active('qwen27')['current']==before['previous'] and active('qwen27')['high_water_sequence']==2
  probe('qwen27','rollback1')
  command([launcher,'--root',str(remote/'clients/signed-lifecycle-r3/qwen27'),'rollback'],out/'qwen27-restore.log')
  assert active('qwen27')['current']==before['current'] and active('qwen27')['high_water_sequence']==2
  probe('qwen27','restored2');probe('gemma26','model-aware2')
  assert authority_hash()==expected;state.update(status='passed',binding_unchanged=True)
except BaseException as e:state.update(status='failed',error=str(e));raise
finally:save()
