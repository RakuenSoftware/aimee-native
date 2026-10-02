"""Private CT101 operator: wait for the Gemma diagnostic, then use both GPUs."""
import json
from pathlib import Path
import subprocess
import time

ROOT = Path('/opt/aimee-memory-lab/larger-native-smoke-20260928')
NAME = 'aimee-qwen27-native-smoke-20260928'


def status(**data):
    (ROOT / 'queue-status.json').write_text(json.dumps(dict(data, updated=time.time()), indent=2) + '\n')


def main():
    previous = 'aimee-gemma26-weight-probe-20260928-r2'
    status(status='waiting_for_gemma_diagnostic')
    while True:
        state = json.loads(subprocess.check_output(['podman', 'inspect', previous], stderr=subprocess.DEVNULL))[0]['State']
        if not state['Running']:
            break
        time.sleep(10)
    assert (ROOT / 'qwen27-fixture-r2/config.json').is_file(), 'Rust publication must finish first'
    args = ['podman', 'run', '-d', '--name', NAME, '--network', 'none', '--ipc', 'host',
        '--device', '/dev/kfd', '--device', '/dev/dri/renderD128', '--device', '/dev/dri/renderD129',
        '--memory', '36g', '--memory-swap', '36g',
        '-v', str(ROOT) + ':/evidence', '-v', str(ROOT / 'private') + ':/private:ro',
        '-v', str(ROOT / 'qwen27-fixture-r2') + ':/fixture:ro',
        '-v', '/opt/aimee-memory-lab/model:/model:ro',
        '-v', '/opt/aimee-memory-lab/qwen27-release-20260928:/weights:ro',
        '-e', 'VLLM_PLUGINS=aimee_native', '-e', 'AIMEE_GGUF_ENABLE=1',
        '-e', 'VLLM_USE_V2_MODEL_RUNNER=0', '-e', 'VLLM_ROCM_USE_AITER=0',
        '-e', 'PYTHONPATH=/private', '-e', 'AIMEE_KERNEL_BANK=',
        '-e', 'AIMEE_EXPORT_KERNELS=/evidence/qwen27-kernels',
        '-e', 'AIMEE_VLLM_CONFIG=/fixture/config.json', '--entrypoint', 'python',
        '79d7f03eedc74943f2ffd9c1271141086ea0813bcd3f697c718e09501908cf58',
        '/evidence/larger_native_smoke.py', 'run', '--profile', 'qwen27',
        '--output', '/evidence/qwen27-result.json']
    (ROOT / 'qwen27-command.json').write_text(json.dumps(args, indent=2) + '\n')
    subprocess.run(args, capture_output=True, check=True)
    status(status='running', container=NAME)
    code = int(subprocess.check_output(['podman', 'wait', NAME], text=True).strip())
    with (ROOT / 'qwen27-run.log').open('w') as log:
        subprocess.run(['podman', 'logs', NAME], stdout=log, stderr=subprocess.STDOUT, check=True)
    status(status='complete' if code == 0 else 'failed', exit_code=code,
           scope='Inspect recorded outcomes; completion is not a release pass')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        status(status='failed', error=repr(error))
        raise
