from pathlib import Path
import json, subprocess, time, hashlib
r=Path('/var/lib/aimee-large-release-validation');out=r/'qwen-update-transfer-r7';out.mkdir(exist_ok=False)
client=r/'clients/signed-lifecycle-r3/qwen27';original=(client/'active.json').read_bytes();before=json.loads(original);assert before['high_water_sequence']==1
state={'status':'installing','started':time.time(),'before':before,'scope':'Single CPU-only signed update retry after diagnosed origin send timeout and release-only 300-second correction; GPU tests remain independent.'}
def save():(out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
save()
try:
 with (out/'install.log').open('w') as log:
  p=subprocess.run(['pct','exec','110','--','/opt/aimee-large-release-validation/assembly/aimee-native-lab','--root','/opt/aimee-large-release-validation/clients/signed-lifecycle-r3/qwen27','install','lab-qwen3.8-27b-q8-native'],stdout=log,stderr=subprocess.STDOUT)
 state['exit_code']=p.returncode;state['after']=json.loads((client/'active.json').read_text())
 if p.returncode:
  state['active_bytes_unchanged']=(client/'active.json').read_bytes()==original
  assert state['active_bytes_unchanged'];state['status']='failed'
 else:
  assert state['after']['high_water_sequence']==2 and state['after']['previous']==before['current'];state['status']='installed'
finally:
 state['finished']=time.time();save()
