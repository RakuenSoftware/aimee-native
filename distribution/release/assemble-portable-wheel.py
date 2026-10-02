#!/usr/bin/env python3
"""Bundle compiled Aimee consumers into a vLLM plugin wheel; never bundle the runtime."""
import argparse
import base64
import configparser
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile
from urllib.parse import urlsplit
import re
import subprocess


def check_glibc(path, ceiling=(2, 34)):
    symbols = subprocess.run(['objdump', '-T', str(path)], check=True,
                             capture_output=True, text=True).stdout
    required = [tuple(map(int, match.groups())) for match in
                re.finditer(r'GLIBC_(\d+)\.(\d+)(?!\.)', symbols)]
    if required and max(required) > ceiling:
        raise ValueError(f'{path} requires glibc {max(required)}, above {ceiling}')


def assemble(wheel, launcher, library, notices, output, gguf_wheel_url, gguf_wheel_sha256,
             version='0.2.2', compiler_dir=None):
    if tuple(map(int, version.split('.')[:3])) >= (0, 2, 3) and compiler_dir is None:
        raise ValueError('Self-hosted native release requires compiled local encoder')
    url = urlsplit(gguf_wheel_url)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
        raise ValueError('Expected credential-free HTTPS dependency URL')
    if not re.fullmatch('[0-9a-f]{64}', gguf_wheel_sha256):
        raise ValueError('Expected dependency SHA-256')
    with zipfile.ZipFile(wheel) as src:
        files = {name: src.read(name) for name in src.namelist() if not name.endswith('/')}
    metadata = [name for name in files if name.endswith('.dist-info/METADATA')]
    if len(metadata) != 1:
        raise ValueError('Expected one distribution')
    info = metadata[0].rsplit('/', 1)[0]
    if not info.startswith('aimee_vllm-'):
        raise ValueError('Expected compiled aimee-vllm wheel')
    # A new version is required so pip upgrades earlier development wheels.
    old_info = info
    info = f'aimee_vllm-{version}.dist-info'
    files = {(info + name[len(old_info):] if name.startswith(old_info + '/') else name): data
             for name, data in files.items()}
    files[info + '/METADATA'] = re.sub(rb'(?m)^Version: [^\r\n]+', f'Version: {version}'.encode(), files[info + '/METADATA'])
    for name in files:
        if name.startswith('aimee_vllm/') and name.endswith(('.py', '.pyc', '.pyx', '.c')) and name not in ('aimee_vllm/__init__.py', 'aimee_vllm/_k.py', 'aimee_vllm/_d.py'):
            raise ValueError('Private implementation source in wheel: ' + name)
    client = (Path(__file__).resolve().parents[1] / 'vllm/aimee_vllm/client.py').read_text()
    client = client.replace('from .compatibility import check_runtime',
                            'from ._p15 import check_runtime')
    files['aimee_vllm/client.py'] = client.encode()
    files['aimee_vllm/native/aimee-native'] = launcher.read_bytes()
    files['aimee_vllm/native/libaimee_native.so'] = library.read_bytes()
    if compiler_dir is not None:
        modules = ('_c0', '_c1', '_c2', '_c3', '_c4', '_c5')
        files['aimee_vllm/native_compiler/__init__.py'] = b''
        for module in modules:
            matches = list(compiler_dir.glob(module + '.*.so'))
            if len(matches) != 1 or matches[0].read_bytes()[:4] != b'\x7fELF':
                raise ValueError('Missing compiled local encoder: ' + module)
            files['aimee_vllm/native_compiler/' + matches[0].name] = matches[0].read_bytes()
    for path in [launcher, library]:
        if path.read_bytes()[:4] != b'\x7fELF':
            raise ValueError('Expected compiled ELF: ' + str(path))
        check_glibc(path)
    if compiler_dir is not None:
        for module in modules:
            check_glibc(next(compiler_dir.glob(module + '.*.so')))
    for path in notices.rglob('*'):
        if path.is_file():
            files[info + '/licenses/' + str(path.relative_to(notices))] = path.read_bytes()
    entries = configparser.ConfigParser()
    entries.read_string(files[info + '/entry_points.txt'].decode())
    entries['console_scripts']['aimee-native'] = 'aimee_vllm.client:main'
    buf = io.StringIO(); entries.write(buf)
    files[info + '/entry_points.txt'] = buf.getvalue().encode()
    headers, _, body = files[info + '/METADATA'].decode().partition('\n\n')
    compiler_requirements = ('\nRequires-Dist: accelerate>=1.15,<2'
        '\nRequires-Dist: gguf>=0.19,<0.20') if compiler_dir is not None else ''
    headers = headers.rstrip('\n') + compiler_requirements + ('\nProvides-Extra: gguf\nRequires-Dist: vllm-gguf-plugin @ '
        + gguf_wheel_url + '#sha256=' + gguf_wheel_sha256 + ' ; extra == "gguf"\n')
    files[info + '/METADATA'] = (headers + '\n' + body).encode()
    files['aimee_vllm/native/compatibility.json'] = json.dumps({
        'schema': 2, 'vllm': '>=0.30.0,<0.31', 'backends': ['cuda', 'hip'],
        'gpu_arch': 'runtime', 'tensor_bridge': 'public-torch-api',
        'scope': 'Runtime-compiled GPU operations. Execution coverage is recorded separately.'
    }, indent=2).encode()
    record = info + '/RECORD'
    files.pop(record, None)
    hashes = io.StringIO(); writer = csv.writer(hashes, lineterminator='\n')
    for name, data in sorted(files.items()):
        writer.writerow([name, 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('='), len(data)])
    writer.writerow([record, '', '']); files[record] = hashes.getvalue().encode()
    output.mkdir(parents=True, exist_ok=True)
    parts = wheel.name.split('-')
    if len(parts) != 5:
        raise ValueError('Expected untagged input wheel')
    parts[1] = version
    dest = output / '-'.join(parts[:2] + ['1'] + parts[2:])
    with dest.open('xb') as f, zipfile.ZipFile(f, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            item = zipfile.ZipInfo(name, (2026, 9, 30, 0, 0, 0)); item.create_system = 3
            item.external_attr = (0o100755 if name.endswith('/aimee-native') else 0o100644) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(item, data)
    return dest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('wheel', 'launcher', 'library', 'notices', 'output'):
        p.add_argument('--' + name, required=True, type=Path)
    p.add_argument('--gguf-wheel-url', required=True)
    p.add_argument('--gguf-wheel-sha256', required=True)
    p.add_argument('--version', default='0.2.2')
    p.add_argument('--compiler-dir', type=Path)
    a = p.parse_args()
    print(assemble(a.wheel, a.launcher, a.library, a.notices, a.output, a.gguf_wheel_url, a.gguf_wheel_sha256, a.version, a.compiler_dir))
