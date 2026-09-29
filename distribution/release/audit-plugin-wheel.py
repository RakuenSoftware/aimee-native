#!/usr/bin/env python3
"""Check complete plugin packaging and wheel RECORD; does not claim GPU correctness."""
import argparse
import base64
import csv
from email.parser import BytesParser
import hashlib
import io
import json
from pathlib import Path
import zipfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('wheel', type=Path)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
with zipfile.ZipFile(a.wheel) as z:
    names = z.namelist()
    assert len(names) == len(set(names)), 'duplicate members'
    info = next(n.rsplit('/', 1)[0] for n in names if n.endswith('.dist-info/METADATA'))
    metadata = BytesParser().parsebytes(z.read(info + '/METADATA'))
    assert 'gguf' in metadata.get_all('Provides-Extra', []), 'GGUF extra not in parsed metadata'
    assert any('vllm-gguf-plugin @ https://' in v and '#sha256=' in v for v in metadata.get_all('Requires-Dist', []))
    assert any('gguf==0.19.0' in v for v in metadata.get_all('Requires-Dist', []))
    entries = z.read(info + '/entry_points.txt').decode()
    assert 'aimee_native = aimee_vllm:register' in entries
    assert 'aimee-native = aimee_vllm.client:main' in entries
    root = 'aimee_vllm/native/'
    assert z.getinfo(root + 'aimee-native').external_attr >> 16 & 0o111
    for n in ['aimee-native', 'libaimee_native.so']:
        assert z.read(root + n).startswith(b'\x7fELF')
    for n in names:
        assert n.startswith(('aimee_vllm/', info + '/'))
        assert not Path(n).is_absolute() and '..' not in Path(n).parts
        assert not n.endswith(('.gguf', '.safetensors', '.pt', '.pth', '.pyc', '.c', '.cpp', '.pyx'))
        if n.endswith('.py'): assert n in ['aimee_vllm/__init__.py', 'aimee_vllm/client.py']
    records = list(csv.reader(io.StringIO(z.read(info + '/RECORD').decode())))
    assert {r[0] for r in records} == set(names)
    for n, digest, size in records:
        if n == info + '/RECORD': continue
        data = z.read(n)
        assert len(data) == int(size)
        assert digest == 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
    manifest = json.loads(z.read(root + 'kernels/manifest.json'))
    for kernel in manifest['kernels']:
        for n in kernel['files']: assert root + 'kernels/' + n in names
    report = {'status': 'passed', 'scope': __doc__, 'wheel': a.wheel.name,
              'sha256': hashlib.sha256(a.wheel.read_bytes()).hexdigest(), 'bytes': a.wheel.stat().st_size,
              'members': len(names), 'kernels': len(manifest['kernels']),
              'compatibility': json.loads(z.read(root + 'compatibility.json')),
              'native_library_sha256': hashlib.sha256(z.read(root + 'libaimee_native.so')).hexdigest(),
              'connection_client_sha256': hashlib.sha256(z.read(root + 'aimee-native')).hexdigest()}
a.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
