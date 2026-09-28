"""Record package relationships and payloads for OS notice gaps; no inference of approval."""
from pathlib import Path
import json
import subprocess
import sys

inventory=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);assert not out.exists()
rows=[]
for row in inventory['os_packages']:
    if row['binary'] not in inventory['gaps']['os_without_notice']:
        continue
    package=row['binary']
    fields='${binary:Package}\n${Version}\n${Source}\n${Depends}\n${Description}\n'
    metadata=subprocess.check_output(['dpkg-query','-W','-f='+fields,package],text=True)
    paths=subprocess.check_output(['dpkg-query','-L',package],text=True).splitlines()
    files=[]
    for name in paths:
        p=Path(name)
        if not p.is_file() or p.is_symlink():continue
        size=p.stat().st_size
        with p.open('rb') as f:head=f.read(4096)
        # Retain only short evidence excerpts from package-owned files. These
        # are vendor SDK files, never Aimee source, memory, or account data.
        snippet=None
        if p.suffix in {'.h','.hpp','.cl','.cmake'}:
            text=head.decode(errors='replace')
            if 'copyright' in text.lower() or 'license' in text.lower():snippet=text
        files.append({'path':name,'bytes':size,'elf':head.startswith(b'\x7fELF'),
                      'static_archive':head.startswith(b'!<arch>'),'notice_excerpt':snippet})
    rows.append({'package':package,'metadata':metadata,'regular_files':files})
out.write_text(json.dumps({'scope':__doc__,'packages':rows},indent=2)+'\n')
