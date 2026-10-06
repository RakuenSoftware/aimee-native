"""Operational capacity guard for the owned test only; no science changes."""
import subprocess,json,time,os,signal
from pathlib import Path
BASE=Path('/opt/jmlr-second-review-20261005/repair-cache/gemma-composition-candidate-r1')
OUT=Path('/mnt/pve/backup/aimee-experiments/root-evacuation-20261005-r1/gemma-composition-candidate-r1/capacity-recovery-r6')
UNIT='jmlr-gemma-prefix-integration-recovery-20261006-r6.service'
RUNNER=str(BASE/'gpu-executor-recovery-r6/run_integration.py')
OUT.mkdir(exist_ok=False,mode=0o700)
def reserve():
 fields=subprocess.check_output(['lvs','--noheadings','--units','g','--nosuffix','-o','lv_size,data_percent','storage/storage'],text=True).split()
 return float(fields[0])*(1-float(fields[1])/100)
start=reserve();assert start>=90 and os.statvfs(BASE).f_bavail*os.statvfs(BASE).f_frsize>=10*1024**3
record={'start_reserve_gib':start,'abort_threshold_gib':90.25,'unit':UNIT,'science_changes':False,'aborted':False}
log='/mnt/pve/backup/aimee-experiments/root-evacuation-20261005-r1/gemma-composition-candidate-r1/gpu-validation-recovery-r6/queue-execution.log'
subprocess.run(['systemd-run','--unit='+UNIT.removesuffix('.service'),'--property=MemoryMax=14G','--property=MemorySwapMax=0','--property=OOMPolicy=stop','--property=KillMode=control-group','--property=TimeoutStopSec=90','--property=StandardOutput=append:'+log,'--property=StandardError=append:'+log,'/opt/aimee-native-serving/clean-release-env-build2/bin/python',str(BASE/'gpu-executor-recovery-r6/queue_integration.py')],check=True)
lowest=start
while subprocess.run(['systemctl','is-active','--quiet',UNIT]).returncode==0:
 available=reserve();lowest=min(lowest,available)
 if available<90.25 and not record['aborted']:
  group=subprocess.check_output(['systemctl','show','--property=ControlGroup','--value',UNIT],text=True).strip()
  assert group.startswith('/system.slice/'+UNIT),group
  pids=[int(s) for s in (Path('/sys/fs/cgroup')/group.lstrip('/')/'cgroup.procs').read_text().split()]
  signaled=[]
  for pid in pids:
   try:
    args=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(bytes([0]))
    if RUNNER.encode() in args:os.kill(pid,signal.SIGINT);signaled.append(pid)
   except ProcessLookupError:pass
  record.update(aborted=True,abort_reserve_gib=available,signaled_only_owned_runner_pids=signaled)
  assert signaled,'capacity threshold reached outside inference runner'
 time.sleep(.25)
record['minimum_observed_reserve_gib']=lowest
record['unit_final_state']=subprocess.check_output(['systemctl','show','--property=ActiveState','--value',UNIT],text=True).strip()
with (OUT/'receipt.json').open('x') as f:f.write(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
