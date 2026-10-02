"""Run Qwen only after the current Gemma BF16 diagnostic releases both GPUs."""
import json
import pathlib
import subprocess
import time

ROOT = pathlib.Path('/opt/aimee-memory-lab/qwen27-baseline-20260928')
ROOT.mkdir(exist_ok=True)


def save(**data):
    (ROOT / 'queue-status.json').write_text(json.dumps(dict(data, updated=time.time()), indent=2) + '\n')


def main():
    predecessor = pathlib.Path('/opt/aimee-memory-lab/gemma26-bf16-reference-20260928')
    save(status='waiting_for_gemma_bf16')
    while True:
        pid = int((predecessor / 'pid').read_text())
        stat = pathlib.Path('/proc', str(pid), 'stat')
        if not stat.exists() or stat.read_text().split()[2] == 'Z':
            state = json.loads((predecessor / 'status.json').read_text())
            if state['status'] not in ('complete', 'failed'):
                raise RuntimeError('Gemma diagnostic exited without terminal status')
            break
        time.sleep(15)
    state = json.loads(subprocess.check_output(['podman', 'inspect', 'aimee-gemma26-bf16-reference-20260928'],
                                              stderr=subprocess.DEVNULL))[0]['State']
    if state['Running']:
        raise RuntimeError('Gemma GPU runtime still active')
    plan = json.loads(pathlib.Path('/opt/aimee-memory-lab/qwen27-release-20260928/loader-plan.json').read_text())
    if plan['status'] != 'passed':
        raise RuntimeError('Qwen loading plan not validated')
    save(status='running')
    with (ROOT / 'run.log').open('w') as log:
        subprocess.run(['python3', str(ROOT / 'larger_model_baseline.py'), '--profile', 'qwen27'],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    save(status='complete', scope='Inspect baseline answers; native-memory validation remains required')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        save(status='failed', error=repr(error))
        raise
