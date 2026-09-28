"""Run Gemma native comparison only after the alternate-kernel baseline passes."""
import json
from pathlib import Path
import subprocess
import time

ROOT = Path('/opt/aimee-memory-lab/gemma26-native-smoke-20260928')
SUITE = Path('/opt/aimee-memory-lab/larger-native-smoke-20260928')
NAME = 'aimee-gemma26-native-smoke-20260928'


def status(**data):
    (ROOT / 'queue-status.json').write_text(json.dumps(dict(data, updated=time.time()), indent=2) + '\n')


def main():
    status(status='waiting_for_baseline')
    pid = int(Path('/opt/aimee-memory-lab/gemma26-triton-check-20260928/pid').read_text())
    while True:
        process = Path('/proc', str(pid), 'stat')
        if not process.exists() or process.read_text().split()[2] == 'Z':
            break
        time.sleep(10)
    predecessor = Path('/opt/aimee-memory-lab/gemma26-baseline-20260928-triton-r1')
    result = json.loads((predecessor / 'status.json').read_text())
    if result.get('status') != 'complete' or result.get('exact') != 4:
        status(status='not_run', reason='alternate-kernel baseline did not pass all four checks')
        return
    previous = json.loads(subprocess.check_output(['podman', 'inspect', 'aimee-gemma26-baseline-20260928-triton-r1'], stderr=subprocess.DEVNULL))[0]['State']
    assert not previous['Running'], 'baseline still owns GPUs'
    assert (SUITE / 'gemma26-fixture/config.json').is_file()
    args = ['podman', 'run', '-d', '--name', NAME, '--network', 'none', '--ipc', 'host',
        '--device', '/dev/kfd', '--device', '/dev/dri/renderD128', '--device', '/dev/dri/renderD129',
        '--memory', '36g', '--memory-swap', '36g',
        '-v', str(ROOT) + ':/evidence', '-v', str(SUITE) + ':/suite:ro',
        '-v', str(SUITE / 'private') + ':/private:ro',
        '-v', str(SUITE / 'gemma26-fixture') + ':/fixture:ro',
        '-v', '/opt/aimee-memory-lab/gemma4-moe:/model:ro',
        '-v', '/opt/aimee-memory-lab/gemma26-release-20260928:/weights:ro',
        '-e', 'VLLM_PLUGINS=aimee_native', '-e', 'AIMEE_GGUF_ENABLE=1',
        '-e', 'VLLM_GGUF_USE_CUDA=0',
        '-e', 'VLLM_USE_V2_MODEL_RUNNER=0', '-e', 'VLLM_ROCM_USE_AITER=0',
        '-e', 'PYTHONPATH=/private', '-e', 'AIMEE_KERNEL_BANK=',
        '-e', 'AIMEE_EXPORT_KERNELS=/evidence/kernels',
        '-e', 'AIMEE_VLLM_CONFIG=/fixture/config.json', '--entrypoint', 'python',
        '79d7f03eedc74943f2ffd9c1271141086ea0813bcd3f697c718e09501908cf58',
        '/suite/larger_native_smoke.py', 'run', '--profile', 'gemma26',
        '--output', '/evidence/result.json']
    (ROOT / 'command.json').write_text(json.dumps(args, indent=2) + '\n')
    subprocess.run(args, capture_output=True, check=True)
    status(status='running', container=NAME)
    code = int(subprocess.check_output(['podman', 'wait', NAME], text=True).strip())
    with (ROOT / 'run.log').open('w') as log:
        subprocess.run(['podman', 'logs', NAME], stdout=log, stderr=subprocess.STDOUT, check=True)
    status(status='complete' if code == 0 else 'failed', exit_code=code,
           scope='Inspect recorded outcomes; completion is not a release pass')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        status(status='failed', error=repr(error))
        raise
