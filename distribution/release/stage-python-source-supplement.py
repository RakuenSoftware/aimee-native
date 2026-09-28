#!/usr/bin/env python3
"""Collect the exact installed Python source set without modifying signed candidates."""
from pathlib import Path
import hashlib,json,shutil,urllib.request
root=Path('/opt/aimee-large-release-validation')
out=root/'distribution-addenda-20260928'/'python-source-20260929'
out.mkdir(exist_ok=True)
old=root/'launchpad-source-download-r2'/'python3.12'
base='https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa/+sourcefiles/python3.12/3.12.13-1+jammy1/'
expected={
'python3.12_3.12.13-1+jammy1.dsc':(3632,'50a106961a35474284e0b389fcb7ca2583673cf182e872dcd154e607247c21c3'),
'python3.12_3.12.13.orig.tar.gz':(27262093,'0816c4761c97ecdb3f50a3924de0a93fd78cb63ee8e6c04201ddfaedca500b0b'),
'python3.12_3.12.13-1+jammy1.debian.tar.xz':(181472,'e627f01e092bd335157a27213ff8904770ecb9b8d3de04d8a778b61af0e69c3e')}
rows=[]
for name,(size,sha) in expected.items():
    dest=out/name
    if not dest.exists():
        if (old/name).exists(): shutil.copyfile(old/name,dest)
        else:
            with urllib.request.urlopen(base+name,timeout=45) as r: data=r.read(size+1)
            if len(data)!=size or hashlib.sha256(data).hexdigest()!=sha: raise ValueError(name)
            dest.write_bytes(data)
    with dest.open('rb') as f: actual=hashlib.file_digest(f,'sha256').hexdigest()
    if dest.stat().st_size!=size or actual!=sha: raise ValueError(name)
    rows.append(dict(file=name,bytes=size,sha256=sha,source_url=base+name))
report=dict(status='exact_source_set_collected',source='python3.12',version='3.12.13-1+jammy1',files=rows,limitations=['DSC signature retained but not independently authenticated; file hashes verified against retained DSC.','Source delivery does not claim reproducible binary identity or complete external fulfillment.'])
(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
(out/'SHA256SUMS').write_text(''.join(x['sha256']+'  '+x['file']+'\n' for x in rows))
print(json.dumps(report))
