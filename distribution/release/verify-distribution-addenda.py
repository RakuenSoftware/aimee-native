#!/usr/bin/env python3
"""Verify recipient access to staged addenda over authenticated TLS."""
import argparse
import hashlib
import json
from pathlib import Path
import ssl
import urllib.parse
import urllib.request

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--url', required=True)
ap.add_argument('--ca', type=Path, required=True)
ap.add_argument('--manifest', type=Path, required=True)
ap.add_argument('--output', type=Path, required=True)
a = ap.parse_args()
context = ssl.create_default_context(cafile=str(a.ca))
expected = a.manifest.read_bytes()
base = a.url.rstrip('/') + '/'
with urllib.request.urlopen(base + 'manifest.json', context=context, timeout=60) as r:
    received = r.read(len(expected) + 1)
if received != expected:
    raise ValueError('Served manifest differs from staged manifest')
rows = []
for item in json.loads(expected)['files']:
    name = item['file']
    if Path(name).name != name:
        raise ValueError('Unexpected addendum path')
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(base + urllib.parse.quote(name), context=context, timeout=120) as r:
        while data := r.read(1024 * 1024):
            size += len(data)
            if size > item['bytes']:
                raise ValueError(f'Oversized artifact: {name}')
            digest.update(data)
    if size != item['bytes'] or digest.hexdigest() != item['sha256']:
        raise ValueError(f'Artifact verification failed: {name}')
    rows.append({'file': name, 'bytes': size, 'sha256': digest.hexdigest(), 'status': 'verified_over_tls'})
report = {'status': 'passed', 'scope': __doc__, 'url': base,
          'manifest_sha256': hashlib.sha256(expected).hexdigest(), 'files': rows,
          'limitation': 'This verifies delivery of collected material, not completeness of source fulfillment.'}
a.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
