#!/usr/bin/env python3
"""Check complete plugin packaging, RECORD integrity and binary disclosure hardening."""
import argparse
import base64
import csv
from email.parser import BytesParser
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

FORBIDDEN_BYTES = (
    b'RakuenSoftware/aimee-qwen',
    b'/opt/aimee-qwen',
    b'/home/',
    b'/Users/',
    b'\\Users\\',
    b'distribution/service/',
    b'distribution/release/',
)
FORBIDDEN_SECTIONS = ('.debug_', '.symtab', '.comment', '.note.gnu.build-id', '.gnu_debuglink', '.gnu_debugdata', '.GCC.command.line', '.llvm_addrsig', '.note.go.buildid', '.note.rustc')


def audit_elf(data, name, temporary):
    path = Path(temporary) / ('artifact-' + hashlib.sha256(name.encode()).hexdigest()[:16])
    path.write_bytes(data)
    sections = subprocess.check_output(['readelf', '-S', str(path)], text=True)
    leaked_sections = [section for section in FORBIDDEN_SECTIONS if section in sections]
    if leaked_sections:
        raise ValueError(f'{name}: disclosure sections retained: {leaked_sections}')
    leaked_markers = [marker.decode('utf-8', 'replace') for marker in FORBIDDEN_BYTES if marker in data]
    if leaked_markers:
        raise ValueError(f'{name}: private/build markers retained: {leaked_markers}')
    exports = []
    if name.endswith('.so'):
        raw = subprocess.check_output(['nm', '-D', '--defined-only', str(path)], text=True)
        exports = [line.split()[-1].split('@')[0] for line in raw.splitlines() if line.split()]
        if name != 'aimee_vllm/native/libaimee_native.so':
            unexpected = [symbol for symbol in exports if not symbol.startswith('PyInit_')]
            if unexpected:
                raise ValueError(f'{name}: unexpected extension exports: {unexpected}')
    return {'name': name, 'sha256': hashlib.sha256(data).hexdigest(),
            'bytes': len(data), 'dynamic_exports': exports}


p = argparse.ArgumentParser(description=__doc__)
p.add_argument('wheel', type=Path)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
with zipfile.ZipFile(a.wheel) as z:
    names = z.namelist()
    assert len(names) == len(set(names)), 'duplicate members'
    info = next(n.rsplit('/', 1)[0] for n in names if n.endswith('.dist-info/METADATA'))
    metadata = BytesParser().parsebytes(z.read(info + '/METADATA'))
    version = tuple(map(int, metadata['Version'].split('.')[:3]))
    assert 'gguf' in metadata.get_all('Provides-Extra', []), 'GGUF extra not in parsed metadata'
    assert any('vllm-gguf-plugin @ https://' in v and '#sha256=' in v for v in metadata.get_all('Requires-Dist', []))
    compatibility = json.loads(z.read('aimee_vllm/native/compatibility.json'))
    portable = compatibility.get('schema') == 2
    if not portable:
        assert any('gguf==0.19.0' in v for v in metadata.get_all('Requires-Dist', []))
    entries = z.read(info + '/entry_points.txt').decode()
    assert 'aimee_native = aimee_vllm:register' in entries
    assert 'aimee-native = aimee_vllm.client:main' in entries
    root = 'aimee_vllm/native/'
    assert z.getinfo(root + 'aimee-native').external_attr >> 16 & 0o111
    for n in ['aimee-native', 'libaimee_native.so']:
        assert z.read(root + n).startswith(b'\x7fELF')
    allowed_python = ['aimee_vllm/__init__.py', 'aimee_vllm/client.py',
                      'aimee_vllm/native_compiler/__init__.py']
    if portable:
        allowed_python += ['aimee_vllm/_k.py', 'aimee_vllm/_d.py']
    public_module_names = ('stream_completion','selection','gguf_loader','control','admission',
                           'backend','binary_kernel','cache','cache_identity','cli','state','store',
                           'worker','runtime_ops','runtime_owner','compatibility')
    for n in names:
        assert n.startswith(('aimee_vllm/', info + '/'))
        if n.startswith('aimee_vllm/') and n.endswith('.so'):
            if any('/' + module + '.' in n for module in public_module_names):
                raise ValueError('descriptive compiled plugin module name in release')
        assert not Path(n).is_absolute() and '..' not in Path(n).parts
        assert not n.endswith(('.gguf', '.safetensors', '.pt', '.pth', '.pyc', '.c', '.cpp', '.pyx'))
        if n.endswith('.py'):
            assert n in allowed_python, 'unexpected Python source in release: ' + n
    if version >= (0, 2, 3):
        requirements = metadata.get_all('Requires-Dist', [])
        assert any(v.startswith('accelerate>=1.15,<2') for v in requirements)
        assert any(v.startswith('gguf>=0.19,<0.20') for v in requirements)
        for module in ('_c0', '_c1', '_c2', '_c3', '_c4', '_c5'):
            assert len([n for n in names if n.startswith('aimee_vllm/native_compiler/' + module + '.') and n.endswith('.so')]) == 1
        for descriptive in (b'publisher', b'checkpoint_weights', b'gguf_weights', b'gemma_compile',
                            b'bounded_compile', b'local_compile', b'native_attention',
                            b'decode_words', b'decode_escapes', b'GemmaCompiler',
                            b'BoundedTextCompiler', b'CheckpointWeights', b'GgufWeights', b'AimeeWorker',
                            b'AimeeAttentionBackend', b'AimeeAttentionImpl', b'NativeAdmission'):
            if any(descriptive in z.read(n) for n in names if n.endswith(('.so', '.py'))):
                raise ValueError('descriptive private identifier in release artifact')
    records = list(csv.reader(io.StringIO(z.read(info + '/RECORD').decode())))
    assert {r[0] for r in records} == set(names)
    for n, digest, size in records:
        if n == info + '/RECORD':
            continue
        data = z.read(n)
        assert len(data) == int(size)
        assert digest == 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
    if portable:
        assert not any(n.endswith(('.hsaco', '.cubin', '.ptx')) or '/kernels/' in n for n in names)
        assert compatibility['gpu_arch'] == 'runtime'
        manifest = {'kernels': []}
    else:
        manifest = json.loads(z.read(root + 'kernels/manifest.json'))
        for kernel in manifest['kernels']:
            for n in kernel['files']:
                assert root + 'kernels/' + n in names
    with tempfile.TemporaryDirectory(prefix='aimee-disclosure-audit-') as temporary:
        elf_members = []
        for n in names:
            data = z.read(n)
            if data.startswith(b'\x7fELF'):
                elf_members.append(audit_elf(data, n, temporary))
    report = {'status': 'passed', 'scope': __doc__, 'wheel': a.wheel.name,
              'sha256': hashlib.sha256(a.wheel.read_bytes()).hexdigest(), 'bytes': a.wheel.stat().st_size,
              'members': len(names), 'kernels': len(manifest['kernels']),
              'compatibility': json.loads(z.read(root + 'compatibility.json')),
              'native_library_sha256': hashlib.sha256(z.read(root + 'libaimee_native.so')).hexdigest(),
              'connection_client_sha256': hashlib.sha256(z.read(root + 'aimee-native')).hexdigest(),
              'disclosure_hardening': {'status': 'passed', 'elf_members': elf_members,
                                       'allowed_python_source': allowed_python,
                                       'forbidden_sections': list(FORBIDDEN_SECTIONS),
                                       'forbidden_markers_checked': len(FORBIDDEN_BYTES)}}
a.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
