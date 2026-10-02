from pathlib import Path
import subprocess,json,fcntl,os,time
r=Path('/var/lib/aimee-large-release-validation');remote=Path('/opt/aimee-large-release-validation');out=r/'model-selection-12b-restore-probe';out.mkdir(exist_ok=False);os.chown(out,100000,100000)
state={'status':'waiting_for_gpu','scope':'Restore paused 12B resident compiler and validate installed model-aware runtime plus interrupted-request recovery.'}
def save():(out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
save()
try:
 with (r/'gpu-validation.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  for ct in [101,110]:
   names=subprocess.check_output(['pct','exec',str(ct),'--','podman','ps','--format','{{.Names}}'],text=True).split();assert all(n=='aimee-native-release-registry' for n in names)
  state['status']='restoring_compiler';save()
  subprocess.run(['pct','exec','101','--','systemctl','start','aimee-native-compiler.service'],check=True,timeout=60)
  deadline=time.monotonic()+900
  while time.monotonic()<deadline:
   ready=subprocess.check_output(['pct','exec','101','--','python3','-c',"from pathlib import Path;import stat; p=Path('/run/aimee-native-compiler/compile.sock');print(p.exists() and stat.S_ISSOCK(p.stat().st_mode))"],text=True).strip()
   if ready=='True':break
   subprocess.run(['pct','exec','101','--','systemctl','is-active','--quiet','aimee-native-compiler.service'],check=True)
   time.sleep(5)
  else:raise TimeoutError('12B compiler readiness')
  state.update(status='probing_installed_12b',compiler_restored=True);save()
  args=['pct','exec','110','--','python3',str(remote/'assembly/live_client_runtime_locked_impl.py'),'--launcher',str(remote/'model-selection-launcher/aimee-native-lab'),'--root','/opt/aimee-client/native-signed-6-validation','--query','What are the native release verification vault code, project, and drink?','--expect','28461','--expect','Juniper','--expect','hibiscus','--repeat','2','--startup-timeout','1200','--port','8177','--interrupt-and-recover','--output',str(remote/out.name/'runtime.json')]
  with (out/'operator.log').open('x') as log:subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,check=True)
  result=json.loads((out/'runtime.json').read_text());assert result['status']=='passed' and result['interrupted_request_recovery']['status']=='passed'
  state['status']='passed'
except BaseException as e:state.update(status='failed',error=str(e));raise
finally:save()
