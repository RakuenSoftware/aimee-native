"""Build the private lab launcher with both HTTPS and OCI release trust configured."""
from pathlib import Path
import hashlib
import json
import os
import subprocess

SOURCE = Path('/opt/aimee-memory-lab/larger-launcher-check-20260928')
TARGET = Path('/opt/aimee-memory-lab/vllm-native-build/distribution/launcher/target')
ORIGIN = Path('/opt/aimee-native-release')
OUT = Path('/opt/aimee-large-release-validation/assembly')


def main():
    ca = ORIGIN / 'ca.pem'
    key = (ORIGIN / 'release-public.hex').read_text().strip()
    assert len(bytes.fromhex(key)) == 32
    assert 'BEGIN CERTIFICATE' in ca.read_text()
    env = dict(os.environ, PATH='/root/.cargo/bin:' + os.environ['PATH'],
        CARGO_TARGET_DIR=str(TARGET), AIMEE_RELEASE_PUBLIC_KEY=key,
        AIMEE_RELEASE_URL='https://192.168.0.126:8445/validation/larger',
        AIMEE_LAB_CA_FILE=str(ca), AIMEE_RELEASE_CA_PEM=ca.read_text())
    with (OUT / 'launcher-build-r5.log').open('x') as log:
        for command in [['cargo', 'test', '--locked', '--offline', '--features', 'lab-release'],
                        ['cargo', 'build', '--release', '--locked', '--offline', '--features', 'lab-release']]:
            subprocess.run(command, cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    binary = TARGET / 'release/aimee-native'
    report = {'status': 'built', 'scope': __doc__, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
        'release_ca_sha256': hashlib.sha256(ca.read_bytes()).hexdigest(),
        'release_public_key': key, 'validation_origin': env['AIMEE_RELEASE_URL'],
        'source_sha256': {str(p.relative_to(SOURCE)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [SOURCE / 'Cargo.toml', SOURCE / 'Cargo.lock', *sorted((SOURCE / 'src').glob('*.rs'))]}}
    (OUT / 'launcher-build-r5.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
