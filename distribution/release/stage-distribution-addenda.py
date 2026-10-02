#!/usr/bin/env python3
"""Stage collected notices/source on a controlled release origin; no release promotion."""
import argparse
import hashlib
import json
import os
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--shared-root', type=Path, required=True)
ap.add_argument('--release-root', type=Path, required=True)
ap.add_argument('--notice-sha256', required=True)
a = ap.parse_args()
root = a.shared_root / 'distribution-addenda-20260928'
items = [
    ('notices.tar.gz', root / 'notices.tar.gz', a.notice_sha256,
     'Consolidated retained third-party notices; component scope qualifications remain in manifest.'),
    ('rocgdb-48b1d324.tar.gz', root / 'rocgdb-48b1d324.tar.gz',
     '079fe5b5e7eb67dd0a56a61b3e78bf7775e50bfc347f61b9e591ea4c1c2020bb',
     'Matching upstream ROCm release source and build instructions; not reproducible-build proof.'),
    ('third-party-source-partial-20260928.tar', a.shared_root / 'third-party-source-partial-20260928.tar',
     '09ef5f33a2245f8250145d99f47403c55e8b5fabedfb70024bce8613046ea515',
     '263 exact OS source/version pairs; collection gap is not a count of established source obligations.'),
]
records = []
for name, path, expected, scope in items:
    with path.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    if digest != expected:
        raise ValueError(f'Hash mismatch: {name}')
    dest = root / name
    if path != dest and not dest.exists():
        dest.symlink_to(path)
    if dest.resolve() != path.resolve():
        raise ValueError(f'Unexpected destination: {dest}')
    records.append({'file': name, 'sha256': digest, 'bytes': path.stat().st_size, 'scope': scope})
report = {'scope': __doc__, 'status': 'collected_material_staged', 'files': records,
          'limitations': ['External distribution fulfillment remains under review.',
                          'No private implementation, model weights or account credentials included.']}
(root / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
(root / 'SHA256SUMS').write_text(''.join(r['sha256'] + '  ' + r['file'] + '\n' for r in records))
link = a.release_root / 'third-party' / '20260928'
link.parent.mkdir(parents=True, exist_ok=True)
if link.exists() or link.is_symlink():
    if link.resolve() != root.resolve():
        raise ValueError(f'Unexpected release destination: {link}')
else:
    staged = link.with_name(link.name + '.next')
    staged.symlink_to(root, target_is_directory=True)
    os.replace(staged, link)
print(json.dumps(report))
