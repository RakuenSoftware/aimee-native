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
# Independently audit all rows, including the final round which has no capture step.
p=subprocess.run(['pct','exec','113','--','python3','-c',"import json,pathlib,sys; r=pathlib.Path('/opt/swe-native/source-learning-20260927'); sys.path.insert(0,str(r)); from resume_campaign import validate_resume; tasks=json.loads((r/'tasks.json').read_text()); validate_resume(r,tasks,len(tasks))"],capture_output=True,text=True)
if p.returncode:
 save({'status':'blocked_by_incomplete_learning_results','error':p.stderr});raise SystemExit(1)
save({'status':'waiting_for_broader_source_learning'})
while True:
 p=subprocess.run(['pct','exec','113','--','cat','/opt/swe-native/broader-source-learning-20260928/status.json'],capture_output=True,text=True)
 if p.returncode:save({'status':'failed','stage':'broader_status','error':p.stderr});raise SystemExit(1)
 broader=json.loads(p.stdout)
 if broader['status']=='complete':break
 if broader['status']=='failed':save({'status':'blocked_by_broader_learning_failure','error':broader.get('error'),'errors':broader.get('errors')});raise SystemExit(1)
 probe=subprocess.run(['pct','exec','113','--','python3','-c',"import pathlib; r=pathlib.Path('/opt/swe-native/broader-source-learning-20260928'); pid=int((r/'pid').read_text()); cmd=(pathlib.Path('/proc')/str(pid)/'cmdline').read_bytes(); assert b'broader_source_learning.py' in cmd"],capture_output=True,text=True)
 if probe.returncode:save({'status':'blocked_by_broader_worker_exit','error':probe.stderr});raise SystemExit(1)
 time.sleep(30)
# Check the actual two-condition result set, not just the controller's status.
probe=subprocess.run(['pct','exec','113','--','python3','-c',"import pathlib,json; r=pathlib.Path('/opt/swe-native/broader-source-learning-20260928'); tasks=json.loads((r/'tasks.json').read_text()); assert len(tasks)==32; rows=[(t['instance_id'],a,json.loads((r/'results'/a/t['instance_id']/'result.json').read_text())) for t in tasks for a in ('source-control','source-learn-1')]; assert all(row['instance_id']==iid and row['arm']==arm and type(row.get('resolved')) is bool for iid,arm,row in rows)"],capture_output=True,text=True)
if probe.returncode:save({'status':'blocked_by_incomplete_broader_results','error':probe.stderr});raise SystemExit(1)
save({'status':'replaying_residual_repetition'})
with (ROOT/'repetition-replay.log').open('w') as log:
 p=subprocess.run(['pct','exec','113','--','python3','/opt/swe-native/replay_repetition_20260928.py','--fixture','/opt/swe-native/pytest-repetition-replay.json','--output','/opt/swe-native/pytest-repetition-replay-result.json'],stdout=log,stderr=subprocess.STDOUT)
if p.returncode:
 save({'status':'failed','stage':'repetition_replay','returncode':p.returncode});raise SystemExit(p.returncode)
# A completed diagnostic is evidence to inspect, not a passing accuracy gate.
save({'status':'stopping_completed_learning_server'})
p=subprocess.run(['pct','exec','101','--','podman','stop','--time','60','aimee-swe-learning'],capture_output=True,text=True)
(ROOT/'server-stop.log').write_text(p.stdout+p.stderr)
if p.returncode:save({'status':'failed','error':'could not stop learning server cleanly'});raise SystemExit(1)
save({'status':'certifying'})
image='3dd4c184270627bc3724fea622eb7e4edd3b7b1ad2ebd90190b5dbbaeb595acc'
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
# Precision changed, so old BF16 reuse evidence cannot certify FP32 reuse.
# Free the resident model while the isolated CPU comparison owns that RAM.
save({'status':'checking_fp32_preparation_reuse'})
subprocess.run(['pct','exec','101','--','systemctl','stop','aimee-native-compiler'],check=True)
try:
 with (ROOT/'preparation-reuse.log').open('w') as log:
  p=subprocess.run(['pct','exec','101','--','/opt/aimee-memory-lab/venv/bin/python','/opt/aimee-memory-lab/aimee-qwen/distribution/tests/lab/preparation_reuse.py','--output','/opt/aimee-memory-lab/release-candidate-20260927/fp32-preparation-reuse','--source','/opt/aimee-native-compiler','--library','/opt/aimee-native-compiler/libaimee_prepare.so','--compute-dtype','float32'],stdout=log,stderr=subprocess.STDOUT)
finally:
 subprocess.run(['pct','exec','101','--','systemctl','start','aimee-native-compiler'],check=True)
if p.returncode:
 save({'status':'failed','stage':'fp32_preparation_reuse','returncode':p.returncode,'image':image});raise SystemExit(p.returncode)
save({'status':'validating_candidate_client'})
with (ROOT/'candidate-client.log').open('w') as log:
 p=subprocess.run(['pct','exec','110','--','python3','/opt/aimee-client/live_client_runtime.py','--launcher','/opt/aimee-client/bin/aimee-native-candidate-test','--root','/opt/aimee-client/native-candidate-6','--query','What are the native release verification vault code, project, and drink?','--expect','28461','--expect','Juniper','--expect','hibiscus','--output','/opt/aimee-client/release-evidence/candidate-6-runtime.json','--repeat','2'],stdout=log,stderr=subprocess.STDOUT)
if p.returncode:
 save({'status':'failed','stage':'candidate_client','returncode':p.returncode,'image':image});raise SystemExit(p.returncode)
save({'status':'checking_served_preparation_dtype'})
with (ROOT/'preparation-dtype-check.log').open('w') as log:
 p=subprocess.run(['python3','/root/aimee-check-preparation-dtype-20260928.py'],stdout=log,stderr=subprocess.STDOUT)
save({'status':'passed' if p.returncode==0 else 'failed','stage':'served_preparation_dtype','returncode':p.returncode,'image':image})
