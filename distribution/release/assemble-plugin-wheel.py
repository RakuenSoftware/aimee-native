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


def assemble(wheel, launcher, library, kernels, notices, output, gguf_wheel_url, gguf_wheel_sha256):
    url = urlsplit(gguf_wheel_url)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment or any(c.isspace() for c in gguf_wheel_url):
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
    info = 'aimee_vllm-0.1.1.dist-info'
    files = {(info + name[len(old_info):] if name.startswith(old_info + '/') else name): data
             for name, data in files.items()}
    files[info + '/METADATA'] = re.sub(rb'(?m)^Version: [^\r\n]+', b'Version: 0.1.1', files[info + '/METADATA'])
    for name in files:
        if name.startswith('aimee_vllm/') and name.endswith(('.py', '.pyc', '.pyx', '.c')) and name != 'aimee_vllm/__init__.py':
            raise ValueError('Private implementation source in wheel: ' + name)
    files['aimee_vllm/client.py'] = (Path(__file__).resolve().parents[1] / 'vllm/aimee_vllm/client.py').read_bytes()
    files['aimee_vllm/native/aimee-native'] = launcher.read_bytes()
    files['aimee_vllm/native/libaimee_native.so'] = library.read_bytes()
    for path in [launcher, library]:
        if path.read_bytes()[:4] != b'\x7fELF':
            raise ValueError('Expected compiled ELF: ' + str(path))
    manifest = json.loads((kernels / 'manifest.json').read_text())
    names = {'manifest.json'}
    for item in manifest['kernels']:
        names.update(item['files'])
    for name in names:
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or path.suffix in {'.py', '.pyx', '.c', '.cpp', '.ttir', '.ttgir', '.ll', '.ptx'}:
            raise ValueError('Unsafe/private kernel artifact: ' + name)
        files['aimee_vllm/native/kernels/' + name] = (kernels / path).read_bytes()
    for path in notices.rglob('*'):
        if path.is_file():
            files[info + '/licenses/' + str(path.relative_to(notices))] = path.read_bytes()
    entries = configparser.ConfigParser()
    entries.read_string(files[info + '/entry_points.txt'].decode())
    entries['console_scripts']['aimee-native'] = 'aimee_vllm.client:main'
    buf = io.StringIO(); entries.write(buf)
    files[info + '/entry_points.txt'] = buf.getvalue().encode()
    meta = files[info + '/METADATA'].decode()
    headers, sep, body = meta.partition('\n\n')
    headers = headers.rstrip('\n') + ('\nProvides-Extra: gguf\nRequires-Dist: vllm-gguf-plugin @ '
        + gguf_wheel_url + '#sha256=' + gguf_wheel_sha256
        + ' ; extra == "gguf"\nRequires-Dist: gguf==0.19.0; extra == "gguf"')
    files[info + '/METADATA'] = (headers + '\n\n' + body).encode()
    files['aimee_vllm/native/compatibility.json'] = json.dumps({
        'vllm': '0.30.0+rocm723', 'torch': '2.12.0+git6bbd260',
        'triton': '3.7.1+gitf0b55c07', 'gpu_arch': 'gfx1100',
        'scope': 'Validated ROCm profile; additional runtime builds require their own compiled assets.'
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
    parts[1] = '0.1.1'
    dest = output / '-'.join(parts[:2] + ['1'] + parts[2:])
    with dest.open('xb') as f, zipfile.ZipFile(f, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            item = zipfile.ZipInfo(name, (2026, 9, 29, 0, 0, 0)); item.create_system = 3
            item.external_attr = (0o100755 if name.endswith('/aimee-native') else 0o100644) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(item, data)
    return dest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['wheel', 'launcher', 'library', 'kernels', 'notices', 'output']:
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--gguf-wheel-url', required=True)
    p.add_argument('--gguf-wheel-sha256', required=True)
    a = p.parse_args()
    print(assemble(**vars(a)))
