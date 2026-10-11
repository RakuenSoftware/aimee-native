"""Sequential all-GPU calibration; owns only its launched children."""
from pathlib import Path
import os,subprocess,json,datetime,sys
r=Path(sys.argv[1])
python='/opt/aimee-native-serving/clean-release-env-build2/bin/python'
models=[('gemma-e2b','google/gemma-4-E2B-it','/mnt/pve/backup/aimee-experiments/native-top9-20260930/native-capabilities-20261004/models/gemma'),('qwen35','Qwen/Qwen3.5-0.8B','/mnt/pve/backup/aimee-experiments/native-top9-20260930/native-capability-models-20261004/hybrid')]
env=dict(os.environ,HF_HUB_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(r/'tmp'))
try:
    for name,identifier,model in models:
        (r/'calibration-controller-status-r2.json').write_text(json.dumps({'state':'running','receiver':name,'controller_pid':os.getpid(),'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}))
        with (r/(name+'-calibration.log')).open('x') as log:
            subprocess.run([python,str(r/'source-v2/calibrate.py'),'--fixture',str(r/'fixture'),'--execution-freeze',str(r/'execution-freeze-v2.json'),'--out',str(r/('calibration-'+name+'-r1')),'--model',model,'--model-id',identifier],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    (r/'calibration-controller-status-r2.json').write_text(json.dumps({'state':'small-receivers-complete','learner_calibration':'pending','controller_pid':os.getpid()}))
except BaseException as exc:
    (r/'calibration-controller-status-r2.json').write_text(json.dumps({'state':'failed','error':repr(exc),'controller_pid':os.getpid()}));raise
