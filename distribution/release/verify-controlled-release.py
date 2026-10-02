#!/usr/bin/env python3
"""Verify promoted launcher and model manifests as a recipient of the controlled origin."""
import hashlib
import json
from pathlib import Path
import ssl
import subprocess
import tempfile
import urllib.request

ORIGIN = 'https://192.168.0.126:8445'
PINNED_KEY = '5d14ca247841adcc1130a4d95b82ead12ba699c03f2ba45f2f47524abde0c6c2'
LAUNCHER = 'a7ebbb5d0f9493f205ca355fab640f56e31cc686219aa038ac348de4ac4727e6'
MANIFESTS = {
    'gemma4-12b-q8-native': '3577d8041f929ae5376160c276d8136f0ddc4a80247d33f27325f4899f1a8636',
    'gemma4-26b-q8-native': '1041c84fe25d84b5700b5cdf53de6eb78b38021d10689e49583cc3425f876cae',
    'qwen3.8-27b-q8-native': '90e75bcfb3e58bce208e8568d6ea335e89fdf8ecb02a4e055384d164367196bc',
}
context = ssl.create_default_context(cafile='/opt/aimee-native-release/ca.pem')


def get(path, limit):
    with urllib.request.urlopen(ORIGIN + path, context=context, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Unexpected response size: ' + path)
    return data


def main():
    rows = []
    with tempfile.TemporaryDirectory(prefix='aimee-promoted-delivery-') as directory:
        root = Path(directory)
        key = root / 'public.der'
        key.write_bytes(bytes.fromhex('302a300506032b6570032100' + PINNED_KEY))
        def verify(data, signature, expected, name):
            if hashlib.sha256(data).hexdigest() != expected or len(signature) != 64:
                raise ValueError('Identity mismatch: ' + name)
            path = root / name
            path.write_bytes(data)
            sig = root / (name + '.sig')
            sig.write_bytes(signature)
            subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-keyform', 'DER', '-inkey', str(key),
                            '-rawin', '-in', str(path), '-sigfile', str(sig)], check=True, capture_output=True)
            return path
        identity = json.loads(get('/bootstrap/linux-x86_64/identity.json', 65536))
        if identity['public_key'] != PINNED_KEY or identity['sha256'] != LAUNCHER:
            raise ValueError('Unexpected bootstrap identity')
        binary = get('/bootstrap/linux-x86_64/aimee-native', 8 * 1024 * 1024)
        if len(binary) != identity['bytes']:
            raise ValueError('Bootstrap byte count mismatch')
        path = verify(binary, get('/bootstrap/linux-x86_64/aimee-native.sig', 64), LAUNCHER, 'aimee-native')
        path.chmod(0o755)
        help_result = subprocess.run([str(path), '--help'], capture_output=True, text=True, check=True, timeout=30)
        if 'install' not in help_result.stdout or 'connect' not in help_result.stdout:
            raise ValueError('Unexpected launcher command interface')
        for model, digest in MANIFESTS.items():
            prefix = '/linux-x86_64/' + model
            raw = get(prefix + '/manifest.json', 4 * 1024 * 1024)
            verify(raw, get(prefix + '/manifest.sig', 64), digest, model + '.json')
            manifest = json.loads(raw)
            if manifest['model'] != model:
                raise ValueError('Wrong model channel')
            rows.append({'model': model, 'sequence': manifest['sequence'], 'manifest_sha256': digest,
                         'status': 'tls_download_and_signature_verified'})
    report = {'status': 'passed', 'scope': __doc__, 'origin': ORIGIN, 'launcher_sha256': LAUNCHER,
              'launcher_help_executed': True, 'models': rows, 'public_distribution': False,
              'limitation': 'Channel and bootstrap delivery verification; GPU lifecycle evidence is recorded separately.'}
    output = Path('/opt/aimee-large-release-validation/controlled-promotion-delivery-20260928.json')
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
