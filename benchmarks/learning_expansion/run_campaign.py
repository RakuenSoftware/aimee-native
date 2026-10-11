"""Exclusive RTX5080 expansion queue; all mutable output stays on dedicated NAS."""
from pathlib import Path
import datetime,hashlib,json,os,subprocess,time,fcntl
ROOT=Path('/mnt/pve/backup/aimee-experiments/learning-expansion-20261011-r3')
SOURCE=ROOT/'source-r3';PYTHON='/opt/aimee-native-serving/clean-release-env-build2/bin/python'
MODEL='/mnt/pve/backup/aimee-experiments/native-top9-20260930/native-tooling-next-20261004/models/qwen'
env=dict(os.environ,HF_HUB_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(ROOT/'tmp'))
(ROOT/'tmp').mkdir(exist_ok=True)
def status(state,**kw):
 (ROOT/'status.json').write_text(json.dumps({'state':state,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'controller_pid':os.getpid(),**kw},indent=2)+'\n')
def execute(args,name):
 with (ROOT/f'{name}.log').open('x') as log:
  subprocess.run([PYTHON,*map(str,args)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
try:
 status('waiting-for-exclusive-5080')
 while True:
  occupied=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
  ownership=open('/opt/jmlr-second-review-20261005/gpu-exclusive.lock','a')
  available=False
  try:
   fcntl.flock(ownership,fcntl.LOCK_EX|fcntl.LOCK_NB);available=True
  except BlockingIOError:pass
  finally:ownership.close()
  if not occupied and available:break
  status('waiting-for-exclusive-5080',active_gpu_pids=occupied.splitlines(),ownership_lock_available=available);time.sleep(15)
 status('mechanism-tests'); execute([SOURCE/'test_scoped_cache.py'],'mechanism-tests')
 for name,pilot in [('pilot-r1',True),('main-r1',False)]:
  repeats=1 if pilot else 3; run=ROOT/name
  for rep in range(repeats):
   status('running',run=name,repeat=rep)
   with (ROOT/f'{name}-{rep}.log').open('x') as log, (ROOT/f'{name}-{rep}-gpu.csv').open('x') as samples:
    monitor=subprocess.Popen(['nvidia-smi','--query-gpu=timestamp,power.draw,memory.used,utilization.gpu','--format=csv,noheader','-lms','1000'],stdout=samples,stderr=subprocess.DEVNULL)
    try:
     args=[PYTHON,str(SOURCE/'experiment.py'),str(run),'--model',MODEL,'--repeat',str(rep)]+(['--pilot'] if pilot else [])
     child=subprocess.Popen(args,env=env,stdout=log,stderr=subprocess.STDOUT)
     status('running',run=name,repeat=rep,child_pid=child.pid)
     if child.wait()!=0:raise RuntimeError(f'{name} repeat {rep} failed; raw output retained')
    finally:
     monitor.terminate();monitor.wait(timeout=10)
  execute([SOURCE/'score.py',run],name+'-scoring')
  execute([SOURCE/'audit.py',run],name+'-accounting')
 status('complete',pilot_responses=288,main_responses=6480)
except BaseException as exc:
 status('failed',error=repr(exc));raise
