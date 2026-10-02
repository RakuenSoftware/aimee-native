"""Wait for verified signed lifecycle completion before taking the two GPUs."""
import json
import pathlib
import subprocess
import time

ROOT = pathlib.Path('/root/aimee-gemma26-baseline-20260928')
ROOT.mkdir(exist_ok=True)


def save(**data):
    (ROOT / 'status.json').write_text(json.dumps(dict(data, updated=time.time()), indent=2) + '\n')


def main():
    predecessor = pathlib.Path('/root/aimee-signed-lifecycle-20260928')
    save(status='waiting_for_signed_lifecycle')
    while True:
        state = json.loads((predecessor / 'status.json').read_text())
        pid = int((predecessor / 'pid').read_text())
        stat = pathlib.Path('/proc', str(pid), 'stat')
        live = stat.exists() and stat.read_text().split()[2] != 'Z'
        if state['status'] == 'failed':
            raise RuntimeError('signed lifecycle needs intervention')
        if not live:
            if state['status'] != 'passed':
                raise RuntimeError('signed lifecycle exited without passing')
            break
        time.sleep(15)
    # Do not overlap the bounded converter's CPU allocation with model loading.
    converter = pathlib.Path('/root/aimee-qwen27-conversion-20260928')
    save(status='waiting_for_conversion_memory')
    while True:
        pid = int((converter / 'pid').read_text())
        stat = pathlib.Path('/proc', str(pid), 'stat')
        if not stat.exists() or stat.read_text().split()[2] == 'Z':
            break
        time.sleep(15)
    save(status='running_baseline')
    with (ROOT / 'run.log').open('w') as log:
        subprocess.run(['pct', 'exec', '101', '--', 'python3',
            '/opt/aimee-memory-lab/gemma26-baseline-20260928/larger_model_baseline.py'],
            stdout=log, stderr=subprocess.STDOUT, check=True)
    save(status='complete', scope='Inspect baseline outcomes; native-memory validation remains required')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        save(status='failed', error=repr(error))
        raise
