"""Private paired Qwen position check after the Gemma GPU work releases devices."""
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/opt/aimee-memory-lab/qwen27-position-ablation-20260928')
SUITE = Path('/opt/aimee-memory-lab/larger-native-smoke-20260928')


def wait_pid(path):
    pid = int(path.read_text())
    while True:
        proc = Path('/proc', str(pid), 'stat')
        if not proc.exists() or proc.read_text().split()[2] == 'Z':
            return
        time.sleep(10)


def status(**data):
    (ROOT / 'native-queue-status.json').write_text(json.dumps(dict(data, updated=time.time()), indent=2) + '\n')


def main():
    status(status='waiting_for_preparation')
    wait_pid(ROOT / 'pid')
    assert json.loads((ROOT / 'status.json').read_text())['exit_code'] == 0
    config = json.loads(Path('/opt/aimee-native-compiler/resident.json').read_text())
    env = dict(os.environ, AIMEE_NATIVE_LIBRARY=config['library'])
    with (ROOT / 'publish.log').open('w') as log:
        subprocess.run(['/opt/aimee-memory-lab/venv/bin/python', str(ROOT / 'larger_native_smoke.py'),
            'prepare', '--profile', 'qwen27', '--output', str(ROOT / 'fixture'),
            '--prepared', str(ROOT / 'qwen27-negative'), '--publisher', '/opt/aimee-native-compiler',
            '--model', '/opt/aimee-memory-lab/model', '--library', '/opt/aimee/libaimee_native.so'],
            env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    status(status='waiting_for_gemma')
    wait_pid(Path('/opt/aimee-memory-lab/gemma26-native-smoke-20260928/queue.pid'))
    running = subprocess.check_output(['podman', 'ps', '--format', '{{.Names}}'], text=True).splitlines()
    assert not any(name.startswith(('aimee-gemma26-', 'aimee-qwen27-')) for name in running), running
    args = json.loads((SUITE / 'qwen27-command.json').read_text())
    name = 'aimee-qwen27-negative-smoke-20260928'
    args[args.index('--name') + 1] = name
    args[args.index(str(SUITE) + ':/evidence')] = str(ROOT) + ':/evidence'
    args[args.index(str(SUITE / 'qwen27-fixture-r2') + ':/fixture:ro')] = str(ROOT / 'fixture') + ':/fixture:ro'
    (ROOT / 'command.json').write_text(json.dumps(args, indent=2) + '\n')
    subprocess.run(args, capture_output=True, check=True)
    status(status='running', container=name)
    code = int(subprocess.check_output(['podman', 'wait', name], text=True).strip())
    with (ROOT / 'run.log').open('w') as log:
        subprocess.run(['podman', 'logs', name], stdout=log, stderr=subprocess.STDOUT, check=True)
    status(status='complete' if code == 0 else 'failed', exit_code=code,
           scope='Only memory positions changed; inspect outcomes before promoting any profile')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        status(status='failed', error=repr(error))
        raise
