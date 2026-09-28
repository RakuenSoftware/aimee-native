#!/usr/bin/env python3
"""Assemble retained notice evidence; does not certify redistribution rights."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--artifacts', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    base = args.artifacts
    baseline = base / 'larger-third-party-notices-r3-20260928'
    manifest = json.loads((baseline / 'manifest.json').read_text())
    payload = {}
    with tarfile.open(baseline / 'notices.tar.gz') as archive:
        for member in archive:
            if member.isfile() and member.name.startswith('notices/'):
                data = archive.extractfile(member).read()
                digest = hashlib.sha256(data).hexdigest()
                if member.name != f'notices/{digest}.txt':
                    raise ValueError(f'Notice digest mismatch: {member.name}')
                payload[member.name] = data
    supplements = {}
    registry = base / 'pypi-notice-supplement-20260928'
    for item in json.loads((registry / 'initial-report.json').read_text())['results']:
        if not item['notices']:
            continue
        notices = []
        for notice in item['notices']:
            data = (registry / 'notices' / notice['file']).read_bytes()
            if hashlib.sha256(data).hexdigest() != notice['sha256']:
                raise ValueError(item['name'])
            path = f"notices/{notice['sha256']}.txt"
            payload[path] = data
            notices.append(path)
        supplements[item['name']] = {'origin': 'exact-version registry archive', 'notices': notices}
    upstream = base / 'upstream-python-notices-20260928'
    for item in json.loads((upstream / 'report.json').read_text())['results']:
        notices = []
        for notice in item['notices']:
            data = (upstream / notice['file']).read_bytes()
            if hashlib.sha256(data).hexdigest() != notice['sha256']:
                raise ValueError(item['package'])
            path = f"notices/{notice['sha256']}.txt"
            payload[path] = data
            notices.append(path)
        supplements[item['package']] = {
            'origin': 'pinned upstream notice', 'commit': item['commit'],
            'scope': item.get('scope', item.get('version_metadata_match', 'release reference')),
            'notices': notices,
        }
    rows = []
    for package in manifest['python_packages']:
        notices = [n['artifact'] for n in package['notices'] if n.get('status') == 'collected']
        row = {'name': package['name'], 'version': package['version'], 'notices': notices,
               'origin': 'installed runtime'}
        if not notices:
            if package['name'] in supplements:
                row.update(supplements[package['name']])
            elif package['name'] == 'aimee-vllm':
                row['origin'] = 'private package notice supplied separately'
            else:
                raise ValueError(f"Unresolved Python notice: {package['name']}")
        for path in row['notices']:
            if path not in payload:
                raise ValueError(f'Missing notice: {path}')
        rows.append(row)
    report = {
        'scope': 'Consolidated retained notices, not corresponding source or redistribution approval. '
                 'Upstream scope qualifications are preserved. OS package relationships remain separately reviewed.',
        'python_packages': rows, 'os_packages': manifest['os_packages'],
        'common_licenses': manifest['common_licenses'],
        'notice_files': len(payload),
        'packages_without_collected_notice': [r['name'] for r in rows if not r['notices']],
    }
    content = (json.dumps(report, indent=2) + '\n').encode()
    payload['manifest.json'] = content
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'manifest.json').write_bytes(content)
    with (args.output / 'notices.tar.gz').open('wb') as dest:
        with gzip.GzipFile(filename='', fileobj=dest, mode='wb', mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w') as archive:
                for name, data in sorted(payload.items()):
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    info.mode = 0o644
                    archive.addfile(info, io.BytesIO(data))
    files = [args.output / name for name in ['manifest.json', 'notices.tar.gz']]
    (args.output / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in files))
    print(json.dumps({'notice_files': report['notice_files'], 'python_packages': len(rows),
                      'without_notice': report['packages_without_collected_notice']}))


if __name__ == '__main__':
    main()
