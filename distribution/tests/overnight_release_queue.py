"""Operator queue for the designated Proxmox test host; serializes GPU ownership.
Does not sign or promote a production release.
"""
import json,pathlib,subprocess,time
ROOT=pathlib.Path('/root/aimee-release-cert-20260927');ROOT.mkdir(exist_ok=True)
def save(state): (ROOT/'status.json').write_text(json.dumps(dict(state,updated=time.time()),indent=2)+'\n')
save({'status':'waiting_for_source_learning'})
while True:
 p=subprocess.run(['pct','exec','113','--','cat','/opt/swe-native/source-learning-20260927/status.json'],capture_output=True,text=True)
 if p.returncode:save({'status':'observation_retry','error':p.stderr});time.sleep(30);continue
 state=json.loads(p.stdout)
 if state['status']=='complete':break
 if state['status']=='failed':save({'status':'blocked_by_learning_failure','error':state.get('error')});raise SystemExit(1)
 # A stale status file must not leave the release queue waiting indefinitely.
 probe=subprocess.run(['pct','exec','113','--','python3','-c',"import pathlib; r=pathlib.Path('/opt/swe-native/source-learning-20260927'); pid=int((r/'pid').read_text().strip()); cmd=(pathlib.Path('/proc')/str(pid)/'cmdline').read_bytes(); assert b'source_learning.py' in cmd"],capture_output=True,text=True)
 if probe.returncode:
  save({'status':'blocked_by_worker_exit','error':probe.stderr,'last_learning_state':state});raise SystemExit(1)
 time.sleep(30)
save({'status':'stopping_completed_learning_server'})
p=subprocess.run(['pct','exec','101','--','podman','stop','--time','60','aimee-swe-learning'],capture_output=True,text=True)
(ROOT/'server-stop.log').write_text(p.stdout+p.stderr)
if p.returncode:save({'status':'failed','error':'could not stop learning server cleanly'});raise SystemExit(1)
save({'status':'certifying'})
image='8f4503539e29413520e27638f957c573c2e09e99fe219119a921f63deb1ac119'
with (ROOT/'certification.log').open('w') as log:
 p=subprocess.run(['pct','exec','101','--','python3','/opt/aimee-memory-lab/aimee-qwen/distribution/vllm/tests/image_certification.py','--image',image,'--output','/opt/aimee-memory-lab/release-candidate-20260927/exact-image-certification','--profiles','q8','--requests','128','--context-tokens','8192','--gpu-utilization','0.8'],stdout=log,stderr=subprocess.STDOUT)
if p.returncode:
 save({'status':'failed','stage':'standard','returncode':p.returncode,'image':image});raise SystemExit(p.returncode)
save({'status':'certifying_wide'})
with (ROOT/'wide-certification.log').open('w') as log:
 p=subprocess.run(['pct','exec','101','--','python3','/opt/aimee-memory-lab/aimee-qwen/distribution/vllm/tests/wide_image_certification.py','--image',image,'--output','/opt/aimee-memory-lab/release-candidate-20260927/wide-image-certification','--stream','--context-tokens','8192','--gpu-utilization','0.8'],stdout=log,stderr=subprocess.STDOUT)
if p.returncode:
 save({'status':'failed','stage':'wide','returncode':p.returncode,'image':image});raise SystemExit(p.returncode)
save({'status':'upgrading_preparation'})
with (ROOT/'preparation-upgrade.log').open('w') as log:
 p=subprocess.run(['python3','/root/aimee-upgrade-preparation-20260928.py'],stdout=log,stderr=subprocess.STDOUT)
if p.returncode:
 save({'status':'failed','stage':'preparation_upgrade','returncode':p.returncode,'image':image});raise SystemExit(p.returncode)
save({'status':'validating_candidate_client'})
with (ROOT/'candidate-client.log').open('w') as log:
 p=subprocess.run(['pct','exec','110','--','python3','/opt/aimee-client/live_client_runtime.py','--launcher','/opt/aimee-client/bin/aimee-native-candidate-test','--root','/opt/aimee-client/native-candidate-6','--query','What are the native release verification vault code, project, and drink?','--expect','28461','--expect','Juniper','--expect','hibiscus','--output','/opt/aimee-client/release-evidence/candidate-6-runtime.json','--repeat','2'],stdout=log,stderr=subprocess.STDOUT)
if p.returncode:
 save({'status':'failed','stage':'candidate_client','returncode':p.returncode,'image':image});raise SystemExit(p.returncode)
save({'status':'checking_served_preparation_dtype'})
with (ROOT/'preparation-dtype-check.log').open('w') as log:
 p=subprocess.run(['python3','/root/aimee-check-preparation-dtype-20260928.py'],stdout=log,stderr=subprocess.STDOUT)
save({'status':'passed' if p.returncode==0 else 'failed','stage':'served_preparation_dtype','returncode':p.returncode,'image':image})
