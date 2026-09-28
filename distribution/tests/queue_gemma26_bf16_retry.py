"""Retry the original checkpoint with adequate CPU RAM after Qwen releases GPUs."""
import json
import pathlib
import subprocess
import time

ROOT = pathlib.Path('/opt/aimee-memory-lab/gemma26-bf16-memory-retry-20260928')
ROOT.mkdir(exist_ok=True)


def save(**data):
    (ROOT / 'queue-status.json').write_text(json.dumps(dict(data, updated=time.time()), indent=2) + '\n')


def main():
    predecessor = pathlib.Path('/opt/aimee-memory-lab/qwen27-baseline-20260928')
    save(status='waiting_for_qwen_baseline')
    while True:
        pid = int((predecessor / 'queue.pid').read_text())
        stat = pathlib.Path('/proc', str(pid), 'stat')
        if not stat.exists() or stat.read_text().split()[2] == 'Z':
            status = json.loads((predecessor / 'queue-status.json').read_text())['status']
            if status not in ('complete', 'failed'):
                raise RuntimeError('Qwen operator exited without terminal status')
            break
        time.sleep(15)
    state = json.loads(subprocess.check_output(['podman', 'inspect', 'aimee-qwen27-baseline-20260928'],
                                              stderr=subprocess.DEVNULL))[0]['State']
    if state['Running']:
        raise RuntimeError('Qwen runtime still owns GPUs')
    active = subprocess.run(['systemctl', 'is-active', '--quiet', 'aimee-native-compiler']).returncode == 0
    save(status='releasing_idle_compiler_memory', compiler_was_active=active)
    try:
        if active:
            subprocess.run(['systemctl', 'stop', 'aimee-native-compiler'], check=True)
        save(status='running_bf16_reference_64g', compiler_was_active=active)
        with (ROOT / 'run.log').open('w') as log:
            subprocess.run(['python3', str(ROOT / 'larger_model_baseline.py'),
                '--reference-bf16', '--run-suffix', 'memory-r2'],
                stdout=log, stderr=subprocess.STDOUT, check=True)
        save(status='complete', scope='Inspect reference answers; GPU runtime stopped before restoring compiler')
    finally:
        if active:
            subprocess.run(['systemctl', 'start', 'aimee-native-compiler'], check=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        save(status='failed', error=repr(error))
        raise
