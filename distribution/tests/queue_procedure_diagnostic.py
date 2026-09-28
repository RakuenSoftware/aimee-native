"""Designated-host operator: run corrective diagnostic after candidate GPU checks."""
import json
import pathlib
import subprocess
import time

ROOT = pathlib.Path('/root/aimee-procedure-diagnostic-20260928')
ROOT.mkdir(exist_ok=True)
STATE = ROOT / 'status.json'


def save(**fields):
    STATE.write_text(json.dumps(dict(fields, updated=time.time()), indent=2) + '\n')


def ct(number, source):
    return subprocess.check_output(['pct', 'exec', str(number), '--', 'python3', '-'],
                                   input=source, text=True)


def main():
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
p=r/'preparation-profile.json';b=r/'preparation-profile.before-procedure-diagnostic.json'
assert not b.exists(), 'prior diagnostic requires inspection'
shutil.copy2(p,b);d=json.loads(p.read_text());d['worker_config']='/opt/aimee-native-compiler/benchmark-resident.json'
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
        save(status='running_matched_procedure_replay')
        with (ROOT / 'replay.log').open('w') as log:
            subprocess.run(['pct', 'exec', '113', '--', 'python3', '/opt/swe-native/procedure_replay_20260928.py',
                '--fixture', '/opt/swe-native/requests-procedure-fixture-20260928.json',
                '--output', '/opt/swe-native/requests-procedure-replay-result-20260928.json',
                '--ssh-config', '/opt/swe-native/source-learning-20260927/ssh.conf'],
                stdout=log, stderr=subprocess.STDOUT, check=True)
        save(status='complete', scope='Diagnostic finished; inspect results before any efficacy claim')
    finally:
        subprocess.run(['pct', 'exec', '101', '--', 'podman', 'stop', '--time', '60', 'aimee-swe-learning'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        ct(101, r'''import pathlib,shutil
r=pathlib.Path('/opt/aimee-memory-lab/swe-learning-20260926')
shutil.copy2(r/'preparation-profile.before-procedure-diagnostic.json',r/'preparation-profile.json')
''')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        save(status='failed', error=repr(error))
        raise
