"""Resume the designated release queue after correcting FP32 partial reuse.

Preserve original failure and all prior exact-image reports. No signing.
"""
import json
import pathlib
import subprocess
import time

ROOT = pathlib.Path('/root/aimee-release-cert-20260927')
IMAGE = '7303c9e9b0785a8574885594aafe87d8f65b54acdf3a3c20a003901be5f40605'


def save(**fields):
    (ROOT / 'status.json').write_text(json.dumps(dict(fields, updated=time.time()), indent=2) + '\n')


def run(name, command):
    target=ROOT / (name + '.log')
    if target.exists():target=ROOT / (name + '-' + str(time.time_ns()) + '.log')
    with target.open('x') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)


def main():
    state = json.loads((ROOT / 'status.json').read_text())
    client_only = state.get('stage') == 'validating_candidate_client'
    dtype_only = state.get('stage') == 'checking_served_preparation_dtype'
    if state.get('stage') not in ('fp32_preparation_reuse', 'validating_candidate_client', 'checking_served_preparation_dtype') or state['status'] != 'failed':
        raise ValueError('expected preserved FP32 partial-reuse failure')
    (ROOT / ('status-before-client-correction-'+str(time.time_ns())+'.json' if client_only or dtype_only else 'status-before-fp32-reuse-correction.json')).write_text(json.dumps(state, indent=2) + '\n')
    source = r'''import pathlib,json
r=pathlib.Path('/opt/aimee-memory-lab/release-candidate-20260927')
for name in ('exact-image-certification','wide-image-certification','activation-certification'):
 d=json.loads((r/name/'report.json').read_text());assert d['status']=='passed';assert d['image'].removeprefix('sha256:')=='7303c9e9b0785a8574885594aafe87d8f65b54acdf3a3c20a003901be5f40605'
assert json.loads(pathlib.Path('/opt/aimee-native-compiler/resident.json').read_text())['compute_dtype']=='float32'
assert 'identical-complete-input' in pathlib.Path('/opt/aimee-native-compiler/gemma_compile.py').read_text()
'''
    subprocess.run(['pct', 'exec', '101', '--', 'python3', '-'], input=source, text=True, check=True)
    if not (client_only or dtype_only):
        save(status='checking_fp32_preparation_reuse_corrected')
        subprocess.run(['pct', 'exec', '101', '--', 'systemctl', 'stop', 'aimee-native-compiler'], check=True)
        try:
            run('preparation-reuse-corrected', ['pct', 'exec', '101', '--', '/opt/aimee-memory-lab/venv/bin/python',
                '/opt/aimee-memory-lab/aimee-native/distribution/tests/lab/preparation_reuse.py',
                '--output', '/opt/aimee-memory-lab/release-candidate-20260927/fp32-preparation-reuse-corrected',
                '--source', '/opt/aimee-native-compiler', '--library', '/opt/aimee-native-compiler/libaimee_prepare.so',
                '--compute-dtype', 'float32'])
        finally:
            subprocess.run(['pct', 'exec', '101', '--', 'systemctl', 'start', 'aimee-native-compiler'], check=True)
    else:
        subprocess.run(['pct','exec','101','--','python3','-c',
            "import pathlib,json; d=json.loads(pathlib.Path('/opt/aimee-memory-lab/release-candidate-20260927/fp32-preparation-reuse-corrected/report.json').read_text()); assert d['status']=='passed' and len(d['rows'])==9 and all(r['exact'] for r in d['rows'])"],check=True)
    if not dtype_only:
        save(status='validating_candidate_client')
        if client_only:
            subprocess.run(['pct','exec','110','--','python3','-c',
                "import pathlib,json,time; r=pathlib.Path('/opt/aimee-client/release-evidence'); p=r/'candidate-6-runtime.json'; assert not p.exists() or json.loads(p.read_text())['status']!='passed'; stamp=str(time.time_ns()); [(q.rename(q.with_name(q.stem+'-before-retry-'+stamp+q.suffix))) for q in [p,p.with_suffix('.log')] if q.exists()]"],check=True)
        run('candidate-client-profile-corrected' if client_only else 'candidate-client', ['pct', 'exec', '110', '--', 'python3', '/opt/aimee-client/live_client_runtime.py',
            '--launcher', '/opt/aimee-client/bin/aimee-native-candidate-test', '--root', '/opt/aimee-client/native-candidate-6',
            '--query', 'What are the native release verification vault code, project, and drink?',
            '--expect', '28461', '--expect', 'Juniper', '--expect', 'hibiscus',
            '--output', '/opt/aimee-client/release-evidence/candidate-6-runtime.json', '--repeat', '2', '--interrupt-and-recover'])
    else:
        subprocess.run(['pct','exec','110','--','python3','-c',
            "import pathlib,json; r=pathlib.Path('/opt/aimee-client'); d=json.loads((r/'release-evidence/candidate-6-runtime.json').read_text()); assert d['status']=='passed' and len(d['answers'])==2 and all(x['passed'] for x in d['answers']); assert d['interrupted_request_recovery']['status']=='passed'; assert d['active']==json.loads((r/'native-candidate-6/active.json').read_text())"],check=True)
    save(status='checking_served_preparation_dtype')
    run('preparation-dtype-check', ['python3', '/root/aimee-check-preparation-dtype-20260928.py'])
    run('broader-final-grades', ['pct', 'exec', '113', '--', 'python3', '-c',
        "import pathlib,json; r=pathlib.Path('/opt/swe-native/broader-source-learning-20260928'); tasks=json.loads((r/'tasks.json').read_text()); assert len(tasks)==32; rows=[(t['instance_id'],a,json.loads((r/'results'/a/t['instance_id']/'result.json').read_text())) for t in tasks for a in ('source-control','source-learn-1')]; assert all(row['instance_id']==iid and row['arm']==arm and type(row.get('resolved')) is bool for iid,arm,row in rows)"])
    save(status='passed', stage='all_candidate_checks_and_broader_grades', image=IMAGE,
         preparation_reuse='fp32-preparation-reuse-corrected')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        state = json.loads((ROOT / 'status.json').read_text())
        save(status='failed', stage=state.get('status'), error=repr(error), image=IMAGE)
        raise
