"""Schedule coding after first installed success; serialize every later GPU probe.

Does not skip remaining signed lifecycle gates. Stops only the old idle queue,
never an active model or installation. Run on the Proxmox test host.
"""
from pathlib import Path
import fcntl
import json
import os
import signal
import subprocess
import time

ROOT = Path('/var/lib/aimee-large-release-validation')


def live(pid):
    p = Path('/proc') / str(pid) / 'stat'
    return p.exists() and p.read_text().split()[2] != 'Z'


def main():
    log = ROOT / 'assembly/gpu-overlap.json'
    state = {'status': 'waiting_for_first_installed_probe', 'scope': __doc__}
    def save():
        log.write_text(json.dumps(state, indent=2) + '\n')
    save()
    try:
        lock = ROOT / 'gpu-validation.lock'
        with lock.open('x') as handle:
            os.chown(lock, 100000, 100000); lock.chmod(0o600)
            fcntl.flock(handle, fcntl.LOCK_EX)
            code = "import fcntl\nf=open('/opt/aimee-large-release-validation/gpu-validation.lock','a')\ntry:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\nexcept BlockingIOError:raise SystemExit(73)\n"
            result = subprocess.run(['pct', 'exec', '110', '--', 'python3', '-c', code])
            assert result.returncode == 73, 'host/container GPU lock did not exclude a competing owner'
        assert subprocess.run(['pct', 'exec', '110', '--', 'python3', '-c', code]).returncode == 0
        state['cross_container_lock_check'] = 'passed'; save()
        pid = int((ROOT / 'assembly/signed-lifecycle-r5.pid').read_text())
        first = ROOT / 'signed-lifecycle-r5/gemma26/fresh1.json'
        while not first.exists():
            assert live(pid), 'signed coordinator exited before first probe'
            report = json.loads((ROOT / 'signed-lifecycle-r5/status.json').read_text())
            assert report['status'] != 'failed', 'initial installed probe failed'
            time.sleep(3)
        assert json.loads(first.read_text())['status'] == 'passed'
        while True:
            report = json.loads((ROOT / 'signed-lifecycle-r5/status.json').read_text())
            if report['status'] == 'installing_gemma26_sequence2':
                break
            assert report['status'] == 'probing_gemma26_fresh1', 'missed safe scheduling boundary'
            assert live(pid)
            time.sleep(.5)
        old_status = ROOT / 'regression-runs-r3/status.json'
        old = json.loads(old_status.read_text())
        assert old['status'] == 'waiting_for_signed_lifecycle' and not old['profiles']
        old_pid = int((ROOT / 'regression/queue-r3.pid').read_text())
        assert live(old_pid)
        os.kill(old_pid, signal.SIGTERM)
        deadline = time.monotonic() + 15
        while live(old_pid):
            assert time.monotonic() < deadline, 'idle queue did not stop'
            time.sleep(.1)
        old.update(status='stopped_before_gpu', reason='Overlap CPU downloads with coding; all GPU users share a verified lock')
        old_status.write_text(json.dumps(old, indent=2) + '\n')
        # First probe has exited; subsequent invocations acquire the same lock
        # as the new coding coordinator before starting their startup clocks.
        helper = ROOT / 'assembly/live_client_runtime.py'
        original = ROOT / 'assembly/live_client_runtime_before_gpu_lock.py'
        assert not original.exists(); original.write_bytes(helper.read_bytes())
        wrapper = "import runpy,sys\nsys.argv += ['--gpu-lock','/opt/aimee-large-release-validation/gpu-validation.lock']\nrunpy.run_path('/opt/aimee-large-release-validation/assembly/live_client_runtime_locked_impl.py',run_name='__main__')\n"
        stage = helper.with_suffix('.next'); stage.write_text(wrapper); stage.replace(helper)
        runner = ROOT / 'regression/larger_regression_coordinator_r4.py'
        proc = subprocess.Popen(['python3', str(runner)], stdout=(ROOT / 'regression/queue-r4.log').open('w'),
                                stderr=subprocess.STDOUT, start_new_session=True)
        (ROOT / 'regression/queue-r4.pid').write_text(str(proc.pid))
        state.update(status='scheduled', coding_coordinator_pid=proc.pid); save()
    except BaseException as error:
        state.update(status='failed', error=repr(error)); save(); raise


if __name__ == '__main__':
    main()
