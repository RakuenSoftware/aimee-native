"""Sequential, all-GPU recovery queue; aborted runs are never overwritten."""
import datetime,json,os,subprocess,sys
from pathlib import Path
r=Path(sys.argv[1]);source=Path(__file__).parent;p='/opt/aimee-native-serving/clean-release-env-build2/bin/python'
assert str(r).startswith('/mnt/pve/backup/aimee-experiments/')
env=dict(os.environ,HF_HUB_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(r/'tmp'))
commands=[('refinement-e2b-retention-r2',[p,str(source/'refinement_retention.py'),str(r),str(r/'refinement-e2b-retention-r2'),str(r/'acquisition-refinement-recovered-r2')]),('e2b-replay-native-full-r2',[p,str(source/'replay_native_full.py'),str(r),str(r/'e2b-replay-native-full-r2')])]
status=r/'recovery-queue-status-r2.json'
try:
    for name,command in commands:
        status.write_text(json.dumps({'state':'running','stage':name,'pid':os.getpid(),'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}))
        with (r/(name+'.log')).open('x') as log:subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    status.write_text(json.dumps({'state':'complete','utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}))
except BaseException as exc:
    status.write_text(json.dumps({'state':'failed','error':repr(exc),'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}));raise
