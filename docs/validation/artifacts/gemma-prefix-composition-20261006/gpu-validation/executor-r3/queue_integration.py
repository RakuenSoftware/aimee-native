"""Passive owned queue: full corrected campaign first, never claim lock early."""
import json,time,subprocess,hashlib,sys
from pathlib import Path
ROOT=Path('/opt/jmlr-second-review-20261005/repair-cache/gemma-composition-candidate-r1')
NAS=Path('/mnt/pve/backup/aimee-experiments/root-evacuation-20261005-r1/gemma-composition-candidate-r1/gpu-validation')
EXPECTED='0e8ff8850e71f353ac45b547644a37674bd065e8223188f80a9ab98c203dac22'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
try:
 assert digest(NAS/'protocol.json')==EXPECTED
 protocol=json.loads((NAS/'protocol.json').read_bytes())
 manifest=json.loads((NAS/'executor-manifest-r3.json').read_bytes())
 assert manifest['protocol_sha256']==EXPECTED
 for name,h in manifest['executor_sha256'].items():
  p=(ROOT/'gpu-executor-r3'/name).resolve();assert p.is_relative_to((ROOT/'gpu-executor-r3').resolve()) and digest(p)==h,name
 prior=Path(protocol['prerequisite']['receipt']);end=time.monotonic()+24*3600
 print('Passive integration queue: waiting for full corrected SQuAD; no GPU lock held',flush=True)
 while not prior.exists():
  assert not (prior.parent/'failed.json').exists(),'full corrected SQuAD failed'
  assert time.monotonic()<end,'24 hour prerequisite deadline exceeded'
  time.sleep(10)
 print('Prerequisite receipt present; executor independently verifies all maps and GPU freedom',flush=True)
 sys.exit(subprocess.call(['/opt/aimee-native-serving/clean-release-env-build2/bin/python',str(ROOT/'gpu-executor-r3/run_integration.py')]))
except BaseException as e:
 if isinstance(e,SystemExit):raise
 failure={'status':'failed','completed':True,'gpu_released':False,'protocol_sha256':EXPECTED,'protocol_relative_path':'protocol.json','error':repr(e),'gpu_started':False,'note':'Passive prerequisite verification failed; no model inference started'}
 with (NAS/'verified-completion.json').open('x') as f:json.dump(failure,f,indent=2)
 raise
