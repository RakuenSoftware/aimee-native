"""Build the private lab launcher with both HTTPS and OCI release trust configured."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
from urllib.parse import urlsplit

SOURCE = Path('/opt/aimee-memory-lab/larger-launcher-check-20260928')
TARGET = Path('/opt/aimee-memory-lab/vllm-native-build/distribution/launcher/target')
ORIGIN = Path('/opt/aimee-native-release')
OUT = Path('/opt/aimee-large-release-validation/assembly')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--target', type=Path, default=TARGET)
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--record', default='launcher-build-r5')
    parser.add_argument('--binary', type=Path, help='new immutable candidate snapshot')
    parser.add_argument('--normal-release', action='store_true', help='Build without the lab-release feature')
    parser.add_argument('--release-url', help='Explicit HTTPS release origin; required for normal builds')
    args = parser.parse_args()
    if args.normal_release and not args.release_url:
        parser.error('--normal-release requires --release-url')
    release_url = args.release_url or 'https://192.168.0.126:8445/validation/larger'
    url = urlsplit(release_url)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        parser.error('--release-url must be an HTTPS origin/path without credentials, query or fragment')
    source, target, out = args.source, args.target, args.output
    if not args.record or Path(args.record).name != args.record:
        raise ValueError('record must be a filename component')
    out.mkdir(parents=True, exist_ok=True)
    if args.binary is not None and args.binary.exists():
        raise FileExistsError(args.binary)
    ca = ORIGIN / 'ca.pem'
    key = (ORIGIN / 'release-public.hex').read_text().strip()
    assert len(bytes.fromhex(key)) == 32
    assert 'BEGIN CERTIFICATE' in ca.read_text()
    env = dict(os.environ, PATH='/root/.cargo/bin:' + os.environ['PATH'],
        CARGO_TARGET_DIR=str(target), AIMEE_RELEASE_PUBLIC_KEY=key,
        AIMEE_RELEASE_URL=release_url, CARGO_BUILD_JOBS='2',
        AIMEE_LAB_CA_FILE=str(ca), AIMEE_RELEASE_CA_PEM=ca.read_text())
    features = [] if args.normal_release else ['--features', 'lab-release']
    with (out / (args.record + '.log')).open('x') as log:
        for command in [['cargo', 'test', '--locked', '--offline', *features],
                        ['cargo', 'build', '--release', '--locked', '--offline', *features]]:
            subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    binary = target / 'release/aimee-native'
    if args.binary is not None:
        with args.binary.open('xb') as snapshot:
            snapshot.write(binary.read_bytes())
        args.binary.chmod(0o755)
    report = {'status': 'built', 'scope': 'Normal-feature distribution launcher' if args.normal_release else __doc__,
        'lab_release': not args.normal_release, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
        'release_ca_sha256': hashlib.sha256(ca.read_bytes()).hexdigest(),
        'release_public_key': key, 'validation_origin': env['AIMEE_RELEASE_URL'],
        'source_sha256': {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [source / 'Cargo.toml', source / 'Cargo.lock', *sorted((source / 'src').glob('*.rs'))]}}
    (out / (args.record + '.json')).write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
