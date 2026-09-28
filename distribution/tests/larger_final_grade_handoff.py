"""Host-only supervised handoff for the existing Gemma r6 campaign.

Stop only the owned inference server after the final submission enters its CPU
 grader. Retire only the waiting host coordinator; preserve the CT113 campaign,
 its grader, all results and its inherited log descriptor. Collect completion
 independently while the existing GPU-lock waiters proceed.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path('/var/lib/aimee-large-release-validation')
RUN = '/opt/swe-native/larger-regression-resume-r6-20260928/gemma26'
HOST_PID = 437687
CAMPAIGN_PID = 426413
SERVER = 'aimee-larger-coding-resume-r6-gemma26'
GRADER = 'sweb.eval.psf__requests-2193.native-20260926-native-2'

def ct(n, code):
    return subprocess.check_output(['pct', 'exec', str(n), '--', 'python3', '-c', code], text=True)

def main():
    out = ROOT / 'gemma-final-grade-handoff'; out.mkdir(exist_ok=False)
    report = {'status': 'waiting_for_final_submission', 'scope': __doc__}
    def save():
        report['updated'] = time.time()
        p = out / 'status.next'; p.write_text(json.dumps(report, indent=2)+'\n'); p.replace(out / 'status.json')
    save()
    try:
        while True:
            guard = json.loads(ct(113, "import sys,json;sys.path.insert(0,'/opt/swe-native');from larger_gpu_handoff import inspect;print(json.dumps(inspect("+repr(RUN)+")))"))
            if guard['grades_complete']:
                report.update(status='already_graded', guard=guard); save(); return
            process = Path('/proc') / str(HOST_PID)
            if not process.exists() or b'larger_regression_resume_r6_queue.py' not in (process/'cmdline').read_bytes():
                raise RuntimeError('original coordinator missing or changed')
            if guard['gpu_ready']:
                live = ct(113, "from pathlib import Path;p=Path('/proc/426413');print(p.exists() and b'larger_regression.py' in (p/'cmdline').read_bytes())").strip()
                if live != 'True': raise RuntimeError('campaign not live')
                grade = subprocess.run(['pct','exec','113','--','docker','inspect','-f','{{.State.Running}}',GRADER],capture_output=True,text=True)
                if grade.returncode == 0 and grade.stdout.strip() == 'true': break
            time.sleep(5)
        report.update(status='handing_off', guard=guard, retired_host_pid=HOST_PID, preserved_campaign_pid=CAMPAIGN_PID)
        (out/'original-coordinator-status.json').write_bytes((ROOT/'regression-gemma-resume-r6/status.json').read_bytes())
        save()
        subprocess.run(['pct','exec','101','--','podman','stop','-t','30',SERVER],check=True,stdout=subprocess.DEVNULL)
        with (out/'server.log').open('w') as log:
            subprocess.run(['pct','exec','101','--','podman','logs',SERVER],stdout=log,stderr=subprocess.STDOUT,check=True)
        # SIGTERM targets the host parent only, not its subprocess group.
        if process.exists() and b'larger_regression_resume_r6_queue.py' in (process/'cmdline').read_bytes():
            os.kill(HOST_PID, signal.SIGTERM)
        report.update(status='gpu_released_cpu_grade_pending'); save()
        while True:
            state = json.loads(ct(113, "from pathlib import Path;print(Path("+repr(RUN+'/status.json')+").read_text())"))
            if state['status'] in ('complete','failed'):
                (out/'campaign-results.json').write_text(json.dumps(state,indent=2)+'\n')
                report.update(status=state['status'], arms=state.get('arms'), pairs=state.get('pairs')); save(); return
            live = ct(113, "from pathlib import Path;p=Path('/proc/426413/stat');print(p.exists() and p.read_text().split()[2]!='Z')").strip()
            if live != 'True': raise RuntimeError('campaign exited without terminal state')
            time.sleep(10)
    except BaseException as error:
        report.update(status='failed', error=repr(error)); raise
    finally: save()

if __name__ == '__main__': main()
