"""Training-only development pilot, NOT a replacement scored campaign."""
import datetime,fcntl,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
r=Path(sys.argv[1]);out=Path(sys.argv[2]);assert str(out).startswith('/mnt/pve/backup/aimee-experiments/')
out.mkdir(exist_ok=False);(out/'tmp').mkdir()
rt=out/'runtime';rt.mkdir();shutil.copytree(r/'acquisition-runtime-r2/source',rt/'source')
for n in ('tmp','prepared'):(rt/n).mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=Path(__file__).parent
freeze={'status':'development training-only pilot','input_sha256':sha(r/'fixture/learner/families.jsonl'),'max_attempts':3,'threshold':7,'refinement':True,'heldout_evaluation':False,'source':{n:sha(source/n) for n in ('acquire.py','refinement_pilot.py','canonical_store.py')},'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(out/'freeze.json').write_text(json.dumps(freeze,indent=2))
sys.path.insert(0,str(rt/'source'));import run_composition_main as serving
lock=open('/opt/jmlr-second-review-20261005/gpu-exclusive.lock','a');fcntl.flock(lock,fcntl.LOCK_EX)
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
block=rt/'execution';block.mkdir();service=None
try:
    service=serving.Service.__new__(serving.Service);serving.Service.__init__(service,rt,block,False)
    proof=serving.physical_summary(service.control({'op':'metrics'}))
    (out/'residency.json').write_text(json.dumps(proof,indent=2))
    session='refinement-development-'+str(service.process.pid)
    env=dict(os.environ,RETAINED_STUDY_API_KEY='tmlr-local-fixture-only',HF_HUB_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(out/'tmp'))
    subprocess.run([serving.PYTHON,str(source/'acquire.py'),'--training',str(r/'fixture/learner/families.jsonl'),'--out',str(out/'acquisition'),'--url','http://127.0.0.1:18991','--model',serving.MODEL,'--session',session,'--expected-training-sha256',freeze['input_sha256'],'--refine','--max-attempts','3'],env=env,check=True)
    from canonical_store import CanonicalStore
    owner=CanonicalStore(r/'canonical-store-resumed-ready.json')
    with (out/'records.jsonl').open('x') as f:
        for line in (out/'acquisition/proposed_records.jsonl').open():
            f.write(json.dumps(owner.admit(json.loads(line)))+'\n');f.flush();os.fsync(f.fileno())
    records=[json.loads(l) for l in (out/'records.jsonl').open()]
    (out/'completion.json').write_text(json.dumps({'admitted':len(records),'development_only':True,'heldout_not_evaluated':True}))
finally:
    if service is not None:
        service.stop();(out/'producer-termination.json').write_text(json.dumps({'pid':service.process.pid,'exit_code':service.process.poll(),'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}))
