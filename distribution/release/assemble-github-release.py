#!/usr/bin/env python3
"""Reconstruct the signed source asset and verify a staged GitHub release."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess


def assemble(payload, output, key, version):
    subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-inkey', str(key),
        '-rawin', '-in', str(payload / 'manifest.json'),
        '-sigfile', str(payload / 'manifest.sig')], check=True, capture_output=True)
    manifest = json.loads((payload / 'manifest.json').read_text())
    assert manifest['version'] == version
    output.mkdir(parents=True, exist_ok=False)
    for name in ('manifest.json', 'manifest.sig'):
        shutil.copyfile(payload / name, output / name)
    sources = [e for e in manifest['files'] if e['role'] == 'corresponding-source']
    assert len(sources) == 1
    for entry in manifest['files']:
        name = entry['name']
        if Path(name).name != name or name in ('.', '..'):
            raise ValueError('unsafe release asset name')
        if entry['role'] == 'corresponding-source':
            subprocess.run(['python3', str(Path(__file__).with_name('source-archive.py')),
                '--revision', manifest['source_ref'], '--output', str(output / name),
                '--prefix', 'aimee-native-' + version + '/'], check=True)
        else:
            if (payload / name).is_symlink():
                raise ValueError('release payload must contain regular files')
            shutil.copyfile(payload / name, output / name)
    subprocess.run(['python3', str(Path(__file__).with_name('release-bundle.py')), 'verify',
        '--bundle', str(output), '--public-key', str(key), '--expected-version', version], check=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('payload', 'output', 'public-key'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--version', required=True)
    a = p.parse_args()
    assemble(a.payload, a.output, a.public_key, a.version)
