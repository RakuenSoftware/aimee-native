"""Designated-host operator: run corrective diagnostic after candidate GPU checks."""
import json
import pathlib
import subprocess
import time

ROOT = pathlib.Path('/root/aimee-retained-success-20260928')
ROOT.mkdir(exist_ok=True)
STATE = ROOT / 'status.json'


def save(**fields):
    STATE.write_text(json.dumps(dict(fields, updated=time.time()), indent=2) + '\n')


def ct(number, source):
    return subprocess.check_output(['pct', 'exec', str(number), '--', 'python3', '-'],
                                   input=source, text=True)


def main():
    predecessor=pathlib.Path('/root/aimee-requests-literal-task-20260928')
    save(status='waiting_for_requests_comparison')
    while True:
        prior=json.loads((predecessor/'status.json').read_text())
        pid=int((predecessor/'pid').read_text())
        stat=pathlib.Path('/proc',str(pid),'stat')
        live=stat.exists() and stat.read_text().split()[2]!='Z'
        if prior['status']=='failed':raise RuntimeError('Requests comparison failed')
        if not live:
            if prior['status']!='complete':raise RuntimeError('Requests comparison exited incomplete')
            break
        time.sleep(10)
    save(status='waiting_for_candidate_checks')
    queue = pathlib.Path('/root/aimee-release-cert-20260927')
    while True:
        state = json.loads((queue / 'status.json').read_text())
        if state['status'] == 'passed':
            break
        if state['status'] == 'failed' or state['status'].startswith('blocked'):
            raise RuntimeError('candidate checks need intervention: ' + json.dumps(state))
        pid = int((queue / 'pid').read_text())
        if not pathlib.Path('/proc', str(pid)).exists():
            raise RuntimeError('candidate queue exited before passing')
        time.sleep(20)
    # The candidate queue has released its GPU runtimes and completed the FP32
    # migration. Use its resident compiler, not a second model load.
    save(status='starting_isolated_diagnostic_server')
    ct(101, r'''import pathlib,json,shutil
r=pathlib.Path('/opt/aimee-memory-lab/swe-learning-20260926')
assert json.loads(pathlib.Path('/opt/aimee-native-compiler/resident.json').read_text())['compute_dtype']=='float32'
p=r/'preparation-profile.json';b=r/'preparation-profile.before-retained-success.json'
assert not b.exists(), 'prior diagnostic requires inspection'
shutil.copy2(p,b);d=json.loads(p.read_text());d['worker_config']='/opt/aimee-native-compiler/benchmark-resident.json';d['encoding_revision']='native-swe-v3-fp32-full'
p.write_text(json.dumps(d)+'\n')
''')
    try:
        with (ROOT / 'server.log').open('w') as log:
            subprocess.run(['pct', 'exec', '101', '--', 'podman', 'start', 'aimee-swe-learning'],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        ct(113, r'''import time,json,urllib.request
for attempt in range(300):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8170/health',timeout=2) as r:
   if r.status==200:break
 except Exception:pass
 time.sleep(1)
else:raise TimeoutError('diagnostic runtime readiness')
''')
        save(status='running_full_agent_and_official_grading')
        with (ROOT / 'replay.log').open('w') as log:
            subprocess.run(['pct','exec','113','--','env',
                'SWE_RUN_ROOT=/opt/swe-native/retained-success-validation-20260928',
                'SWE_SECONDS=600','SWE_STEPS=40','SWE_OUTPUT_TOKENS=1536',
                'SWE_GRADE_TIMEOUT=900','SWE_ADMISSION_WAIT_SECONDS=660',
                'SWE_GENERATION_TIMEOUT_SECONDS=600','SWE_CAPTURE_FORMAT_FEEDBACK=1',
                '/opt/swe-venv/bin/python','/opt/swe-native/retained-success-validation-20260928/retained_success_validation.py'],
                stdout=log,stderr=subprocess.STDOUT,check=True)
        save(status='complete', scope='Full-task follow-up complete; inspect all ten retained-success outcomes')
    finally:
        subprocess.run(['pct', 'exec', '101', '--', 'podman', 'stop', '--time', '60', 'aimee-swe-learning'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        ct(101, r'''import pathlib,shutil
r=pathlib.Path('/opt/aimee-memory-lab/swe-learning-20260926')
shutil.copy2(r/'preparation-profile.before-retained-success.json',r/'preparation-profile.json')
''')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        save(status='failed', error=repr(error))
        raise
