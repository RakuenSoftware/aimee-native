"""Assemble a private binary candidate from completed larger-model kernel builds."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path('/opt/aimee-memory-lab/larger-binary-client-20260928')
BUILD = 'aimee-larger-client-build-20260928'
BASE = '79d7f03eedc74943f2ffd9c1271141086ea0813bcd3f697c718e09501908cf58'


def main():
    code = int(subprocess.check_output(['podman', 'wait', BUILD], text=True).strip())
    with (ROOT / 'wheel-build.log').open('w') as log:
        subprocess.run(['podman', 'logs', BUILD], stdout=log, stderr=subprocess.STDOUT, check=True)
    if code:
        raise RuntimeError(f'wheel build failed: {code}')
    kernels = ROOT / 'kernels'
    subprocess.run(['podman', 'cp', BUILD + ':/opt/aimee/kernels', str(kernels)], check=True)
    manifest = json.loads((kernels / 'manifest.json').read_text())
    known = {item['identity']: item for item in manifest['kernels']}
    sources = [Path('/opt/aimee-memory-lab/gemma26-native-smoke-20260928/kernels'),
               Path('/opt/aimee-memory-lab/larger-native-smoke-20260928/qwen27-kernels')]
    for source in sources:
        for path in sorted(source.glob('*/manifest.json')):
            for item in json.loads(path.read_text())['kernels']:
                if item['identity'] in known:
                    previous = known[item['identity']]
                    assert previous['signature'] == item['signature'] and previous['constants'] == item['constants']
                    continue
                for name in item['files']:
                    assert Path(name).name == name and name.endswith(('.json', '.hsaco'))
                    target = kernels / name
                    data = (path.parent / name).read_bytes()
                    if target.exists():
                        assert target.read_bytes() == data
                    else:
                        target.write_bytes(data)
                known[item['identity']] = item
    (kernels / 'manifest.json').write_text(json.dumps({'kernels': list(known.values())}, indent=2) + '\n')
    wheels = list((ROOT / 'wheels').glob('*.whl'))
    assert len(wheels) == 1
    (ROOT / 'Containerfile').write_text(f'''FROM {BASE}
COPY wheels/{wheels[0].name} /tmp/aimee-client.whl
RUN python -m pip install --no-deps --force-reinstall /tmp/aimee-client.whl && rm /tmp/aimee-client.whl
COPY kernels/ /opt/aimee/kernels/
'''.replace('/tmp/aimee-client.whl', '/tmp/' + wheels[0].name))
    with (ROOT / 'image-build.log').open('w') as log:
        subprocess.run(['podman', 'build', '--network', 'none', '--pull=never',
                        '--iidfile', str(ROOT / 'image.id'), '-f', str(ROOT / 'Containerfile'), str(ROOT)],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    report = {'status': 'built', 'scope': 'Binary candidate assembly; GPU validation pending',
              'image': (ROOT / 'image.id').read_text().strip(), 'base': BASE,
              'kernel_profiles': len(known),
              'wheel_sha256': hashlib.sha256(wheels[0].read_bytes()).hexdigest(),
              'kernel_manifest_sha256': hashlib.sha256((kernels / 'manifest.json').read_bytes()).hexdigest()}
    (ROOT / 'build.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        (ROOT / 'build-error.json').write_text(json.dumps({'error': repr(error)}) + '\n')
        raise
