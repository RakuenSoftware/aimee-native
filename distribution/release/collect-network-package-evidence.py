"""Inspect the installed vendor networking packages without changing the image.

Collect package-owned text sources/notices for review; no Aimee files are read.
This records contents and license statements, not legal redistribution approval.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

out = Path(sys.argv[1]); out.mkdir(exist_ok=False)
report = {'scope': __doc__, 'packages': []}
for package in ['ionic-common', 'libionic1:amd64', 'libionic-dev:amd64', 'bnxt-rocelib', 'hsa-amd-aqlprofile']:
    paths = subprocess.check_output(['dpkg-query', '-L', package], text=True).splitlines()
    row = {'package': package, 'files': []}
    for name in paths:
        p = Path(name)
        if not p.is_file() or p.is_symlink():
            continue
        size = p.stat().st_size
        with p.open('rb') as f:
            head = f.read(512)
        entry = {'path': name, 'bytes': size, 'elf': head.startswith(b'\x7fELF'),
                 'static_archive': head.startswith(b'!<arch>'), 'script': head.startswith(b'#!')}
        # Only package text source/config/header/notice files. No shared/static
        # libraries, model artifacts, private configs or repository contents.
        if size < 1024 * 1024 and not entry['elf'] and not entry['static_archive']:
            raw = p.read_bytes()
            try:
                raw.decode('utf-8')
            except UnicodeDecodeError:
                pass
            else:
                digest = hashlib.sha256(raw).hexdigest()
                (out / (digest + '.txt')).write_bytes(raw)
                entry.update(sha256=digest, artifact=digest + '.txt')
        row['files'].append(entry)
    report['packages'].append(row)
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
