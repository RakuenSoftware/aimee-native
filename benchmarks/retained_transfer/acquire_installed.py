"""Freeze calibration exclusions, then start a distinct learner process.

The learner API receives only training-export payloads. Successful proposals
remain pending until actual canonical admission/read-back; no scored receivers
are launched here. Never substitutes oracle content.
"""
import datetime,fcntl,hashlib,json,os,shutil,subprocess,sys,time
from collections import defaultdict
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    root=Path(sys.argv[1]);assert str(root).startswith('/mnt/pve/backup/aimee-experiments/')
    while not (root/'calibration-gemma12b-r1/process-termination.json').exists():
        time.sleep(15)
    eligibility={};evidence={}
    for name in ('qwen3','gemma-e2b','qwen35','gemma12b'):
        run=root/('calibration-'+name+'-r1')
        assert json.loads((run/'completion.json').read_text())['passed']
        rows=[json.loads(x) for x in (run/'responses.jsonl').read_text().splitlines()]
        counts=defaultdict(lambda:[0,0])
        for row in rows:
            counts[row['family_id']][0]+=int(row['correct']);counts[row['family_id']][1]+=1
        assert len(rows)==480 and len(counts)==60 and all(n==8 for c,n in counts.values())
        evidence[name]={'responses_sha256':sha(run/'responses.jsonl'),'counts':dict(counts)}
        for family,(correct,n) in counts.items():
            eligibility[family]=eligibility.get(family,True) and correct<2
    ledger={'frozen_before_acquisition':True,'criterion':'Exclude if any receiver scores at least 2/8 on separate calibration inputs; never on heldout inputs',
        'eligible_family_ids':sorted(f for f,v in eligibility.items() if v),'excluded_family_ids':sorted(f for f,v in eligibility.items() if not v),
        'calibration_evidence':evidence,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    with (root/'eligibility.json').open('x') as f:json.dump(ledger,f,indent=2)
    rt=root/'acquisition-runtime';rt.mkdir()
    shutil.copytree(root/'installed-calibration-runtime/source',rt/'source')
    for name in ('tmp','prepared'):(rt/name).mkdir()
    helper=rt/'source/run_composition_main.py'
    text=helper.read_text();assert text.count('max_model_len=2048')==1
    helper.write_text(text.replace('max_model_len=2048','max_model_len=4096'))
    # Only the input/output budget changes; no model or adapter mathematics.
    freeze={'files':{str(p.relative_to(rt)):sha(p) for p in (rt/'source').rglob('*') if p.is_file() and p.suffix in ('.py','.json')},
        'learner_export_sha256':sha(root/'fixture/learner/families.jsonl'),'max_model_len':4096,
        'source_commit':json.loads((root/'acquisition-driver-freeze.json').read_text())['commit'],
        'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'frozen_before_learner_start':True}
    with (root/'acquisition-runtime-freeze.json').open('x') as f:json.dump(freeze,f,indent=2)
    driver_freeze=json.loads((root/'acquisition-driver-freeze.json').read_text())
    for name,digest in driver_freeze['files'].items():assert sha(root/'source-v3'/name)==digest
    lock=open('/opt/jmlr-second-review-20261005/gpu-exclusive.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
    sys.path.insert(0,str(rt/'source'))
    import run_composition_main as serving
    service=None;block=rt/'execution';block.mkdir()
    try:
        service=serving.Service.__new__(serving.Service);serving.Service.__init__(service,rt,block,False)
        proof=serving.physical_summary(service.control({'op':'metrics'}))
        session='learner-A-'+str(service.process.pid)
        with (root/'learner-process-start.json').open('x') as f:json.dump({'session':session,'pid':service.process.pid,
            'start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'physical_residency':proof,
            'calibration_session_distinct':True,'api_tools':False},f,indent=2)
        env=dict(os.environ,RETAINED_STUDY_API_KEY='tmlr-local-fixture-only',HF_HUB_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(root/'tmp'))
        with (root/'acquisition.log').open('x') as log:
            subprocess.run(['/opt/aimee-native-serving/clean-release-env-build2/bin/python',str(root/'source-v3/acquire.py'),
                '--training',str(root/'fixture/learner/families.jsonl'),'--expected-training-sha256',freeze['learner_export_sha256'],
                '--out',str(root/'acquisition-r1'),'--url','http://127.0.0.1:18991','--model',serving.MODEL,'--session',session],
                env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        with (root/'learner-final-residency.json').open('x') as f:json.dump(serving.physical_summary(service.control({'op':'metrics'})),f,indent=2)
    finally:
        if service is not None:
            service.stop()
            with (root/'learner-process-termination.json').open('x') as f:json.dump({'pid':service.process.pid,'exit_code':service.process.poll(),
                'end_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'canonical_admission':'pending authorized store receipt; receivers not launched'},f,indent=2)

if __name__=='__main__':main()
