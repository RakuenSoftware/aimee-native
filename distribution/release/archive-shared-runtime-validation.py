#!/usr/bin/env python3
"""Archive explicitly selected synthetic validation evidence, excluding credentials."""
import argparse
import hashlib
import json
import shlex
import tarfile
from pathlib import Path

ROOT = Path('/opt/aimee-native-serving')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    gates = [ROOT / 'shared-release-live-r10/report.json',
             ROOT / 'shared-enrolled-all-r12-r2/report.json',
             ROOT / 'model-plugins-shared-r12/final-installation.json',
             ROOT / 'shared-runtime-final-deployment.json',
             ROOT / 'shared-release-quality-r12/report.json',
             ROOT / 'model-plugins-shared-r12/installation-isolation/report.json',
             ROOT / 'shared-runtime-source-provenance-r12/current-checks.json']
    for gate in gates:
        if json.loads(gate.read_bytes())['status'] != 'passed':
            raise RuntimeError('incomplete release gate: ' + str(gate))
    secrets = [(ROOT / 'credentials.env').read_text().split('=', 1)[1].strip().encode()]
    core = ROOT / 'core-validation'
    for profile in core.rglob('remote.conf'):
        lines = profile.read_text().splitlines()
        if len(lines) == 2:
            secrets.append(lines[1].encode())
    for name in ('driver.env', 'database.env'):
        for line in (core / name).read_text().splitlines():
            line = line.removeprefix('export ')
            if '=' not in line:
                continue
            key, value = line.split('=', 1)
            if key in ('LIVE_PW', 'LIVE_MIGRATOR_PW', 'LIVE_PG_URL', 'LIVE_PG_ADMIN', 'POSTGRES_PASSWORD'):
                values = shlex.split(value)
                if len(values) == 1:
                    secrets.append(values[0].encode())
    selected = set(gates)
    deployment=json.loads((ROOT / 'shared-runtime-final-deployment.json').read_bytes())
    release=Path(deployment['release']).resolve(strict=True)
    if not release.is_relative_to((ROOT / 'releases').resolve(strict=True)):
        raise RuntimeError('deployment release outside owned immutable releases')
    for name in ('manifest.json', 'catalog.json', 'serving.json'):
        selected.add(release / name)
    roots = [ROOT / name for name in ('shared-gemma-lifecycle-r7', 'shared-resident-gemma-r8',
             'shared-release-live-r10', 'shared-enrolled-all-r11', 'model-plugins-shared-r10',
             'shared-enrolled-all-r12', 'shared-enrolled-all-r12-r2',
             'shared-release-quality-r12', 'model-plugins-shared-r12', 'shared-runtime-deployment-r12', 'shared-runtime-deployment-r12-r2')]
    for directory in roots:
        for path in directory.rglob('*'):
            if path.is_file() and not path.is_symlink() and path.suffix in ('.json', '.jsonl', '.log'):
                selected.add(path)
    for directory in ('enrollment-r2', 'native-connect-r10', 'profile-pinning-r10',
                      'source-export-r10', 'source-export-r10-r2', 'source-authority-r10', 'source-revocation-r10'):
        for name in ('report.json', 'source-probe.json'):
            path = core / directory / name
            if path.is_file():
                selected.add(path)
    for name in ('shared-client-tests-r10-final.log', 'shared-adapter-tests-r10.log',
                 'shared-wheel-isolation-r10-r2.log', 'shared-final-install-r11-r2.log',
                 'shared-adapter-tests-r12-current.log', 'shared-auth-tests-r12.log',
                 'shared-preparation-tests-r12.log', 'shared-final-install-r12.log',
                 'shared-isolation-r12.log', 'shared-client-tests-r12.log',
                 'shared-bridge-tests-r12.log', 'shared-bridge-tests-r12-r2.log',
                 'shared-export-tests-r12.log'):
        selected.add(ROOT / name)
    selected.update((ROOT / 'model-plugins-shared-r12/release').glob('*.whl'))
    selected.update((ROOT / 'shared-runtime-source-provenance-r12').glob('*'))
    selected.update((ROOT / 'release-validation-notices').glob('*.txt'))
    selected.update((ROOT / 'release-validation-notices').glob('*.json'))
    manifest = []
    for path in sorted(selected):
        data = path.read_bytes()
        if any(secret and secret in data for secret in secrets):
            raise RuntimeError('credential-containing evidence excluded; inspect privately: ' + str(path))
        if b'-----BEGIN PRIVATE KEY-----\n' in data or b'-----BEGIN RSA PRIVATE KEY-----\n' in data:
            raise RuntimeError('private key is not evidence')
        manifest.append({'file': str(path.relative_to(ROOT)), 'bytes': len(data),
                         'sha256': hashlib.sha256(data).hexdigest()})
    options.output.mkdir(parents=True)
    archive = options.output / 'raw.tar.gz'
    with archive.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as output:
        for path in sorted(selected):
            output.add(path, arcname=str(path.relative_to(ROOT)), recursive=False)
    report = {'status': 'passed', 'scope': __doc__, 'files': manifest,
              'archive': archive.name, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
              'bytes': archive.stat().st_size, 'credentials_checked': True}
    (options.output / 'archive.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
