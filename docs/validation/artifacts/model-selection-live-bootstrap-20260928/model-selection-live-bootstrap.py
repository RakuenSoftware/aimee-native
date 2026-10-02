from pathlib import Path
import subprocess,json,time,os
r=Path('/var/lib/aimee-large-release-validation');out=r/'model-selection-live-bootstrap';out.mkdir(exist_ok=False);os.chown(out,100000,100000)
state={'status':'waiting_for_deployment','scope':'Live enrolled-account bootstrap and model-selection authorization; no GPU inference.'}
def save():(out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
save()
try:
 deadline=time.monotonic()+900
 while time.monotonic()<deadline:
  d=json.loads(subprocess.check_output(['pct','exec','100','--','cat','/root/model-selection-rollout-r2-20260928/status.json'],text=True))
  if d['status']=='healthy_pending_authorization_tests':break
  if d['status'] in ['rolled_back','rollback_failed']:raise RuntimeError('candidate deployment failed')
  alive=subprocess.run(['pct','exec','100','--','kill','-0','3254856'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
  if not alive:raise RuntimeError('deployment exited before healthy outcome')
  time.sleep(10)
 else:raise TimeoutError('deployment observation deadline')
 models=['google-gemma-4-12b-native-negative-v1']
 for name in ['gemma26','qwen27']:models.append(json.loads((r/'packages'/name/'2/runtime/profile.json').read_text())['native_model'])
 args=['pct','exec','110','--','python3','/opt/aimee-client/live_bootstrap_authority_models.py','--config','/opt/aimee-client/native-signed-6-validation/config.json','--recipient','native-preview','--output','/opt/aimee-large-release-validation/model-selection-live-bootstrap/results.json']
 for m in models:args+=['--model',m]
 state.update(status='testing',models=models);save()
 with (out/'operator.log').open('w') as log:subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=360)
 result=json.loads((out/'results.json').read_text());assert result['status']=='passed'
 state.update(status='passed',cases=len(result['results']))
except BaseException as e:state.update(status='failed',error=str(e));raise
finally:save()
