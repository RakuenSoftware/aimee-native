"""Bounded CT101 scheduling helper: give real installs priority over staging copies.

Only controls the exact staging builder PID/command, never model processes.
Resumes a builder it suspended on stage changes, timeout, or termination.
"""
from pathlib import Path
import json
import os
import signal
import time

ROOT = Path('/opt/aimee-large-release-validation')
PID = int((ROOT / 'normal-staging-20260928/build.pid').read_text())
OUT = ROOT / 'normal-install-io-priority-20260928.json'
stop = False
paused = False
report = {'status': 'monitoring', 'builder_pid': PID, 'events': [], 'scope': __doc__}

def save():
    OUT.write_text(json.dumps(report, indent=2) + '\n')

def terminate(*args):
    global stop
    stop = True

for sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(sig, terminate)

def alive():
    root = Path('/proc') / str(PID)
    if not (root / 'stat').exists():
        return False
    if (root / 'stat').read_text().split()[2] == 'Z':
        return False
    return b'stage_larger_normal.py' in (root / 'cmdline').read_bytes()

try:
    deadline = time.monotonic() + 4 * 3600
    save()
    while not stop and time.monotonic() < deadline and alive():
        state = json.loads((ROOT / 'normal-lifecycle-r2-20260928/status.json').read_text())['status']
        want_pause = state.startswith('installing_')
        if want_pause != paused:
            os.kill(PID, signal.SIGSTOP if want_pause else signal.SIGCONT)
            paused = want_pause
            report['events'].append({'time': time.time(), 'lifecycle': state,
                                     'action': 'suspend_builder' if paused else 'resume_builder'})
            report['status'] = 'prioritizing_install' if paused else 'monitoring'
            save()
        if state in ('passed', 'failed'):
            break
        time.sleep(5)
finally:
    if paused and alive():
        os.kill(PID, signal.SIGCONT)
        report['events'].append({'time': time.time(), 'action': 'resume_builder_on_exit'})
    report.update(status='finished', finished=time.time())
    save()
