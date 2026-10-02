"""Download only resolved exact-version source files, verified against APT hashes.

Does not unpack or execute source archives. Unresolved packages stay unresolved.
The result is one portion of the third-party source bundle, not release approval.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import shutil
import urllib.request
from urllib.parse import urlsplit

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--plan',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
plan=json.loads(a.plan.read_text())
assert plan['status']=='availability_checked'
a.output.mkdir(exist_ok=False)
files={}
for package in plan['packages']:
    if package['status']!='resolved':continue
    for f in package['files']:
        u=urlsplit(f['uri'])
        assert u.scheme in ('http','https') and u.hostname in ('archive.ubuntu.com','security.ubuntu.com')
        assert Path(f['name']).name==f['name'] and f['name'] not in ('.','..')
        assert len(f['index_checksum'])==1
        algorithm,digest=f['index_checksum'][0].split(':',1)
        assert algorithm in ('SHA256','SHA512')
        key=f['name']
        if key in files:assert files[key]['index_checksum']==f['index_checksum'] and files[key]['bytes']==f['bytes']
        else:files[key]=f
required=sum(f['bytes'] for f in files.values())
if shutil.disk_usage(a.output).free < required+8*1024**3:raise RuntimeError('insufficient space with reserve')
report=dict(status='downloading',scope=__doc__,plan_sha256=hashlib.sha256(a.plan.read_bytes()).hexdigest(),
            expected_files=len(files),expected_bytes=required,unresolved_packages=plan['unresolved'],results=[])
def save():
    temporary=a.output/'report.tmp'
    temporary.write_text(json.dumps(report,indent=2)+'\n')
    os.replace(temporary,a.output/'report.json')
def fetch(f):
    destination=a.output/f['name'];partial=a.output/(f['name']+'.partial')
    algorithm,expected=f['index_checksum'][0].split(':',1)
    digest=hashlib.new(algorithm.lower());sha=hashlib.sha256();size=0
    try:
        request=urllib.request.Request(f['uri'].replace('http://','https://',1),headers={'User-Agent':'Aimee-release-source-collector/1'})
        with urllib.request.urlopen(request,timeout=60) as response, partial.open('xb') as out:
            while chunk:=response.read(1024**2):
                size+=len(chunk)
                if size>f['bytes']:raise ValueError('source exceeds indexed size')
                digest.update(chunk);sha.update(chunk);out.write(chunk)
        if size!=f['bytes'] or digest.hexdigest()!=expected:raise ValueError('source size/hash mismatch')
        partial.rename(destination)
        return dict(name=f['name'],status='verified',bytes=size,sha256=sha.hexdigest(),index_checksum=f['index_checksum'])
    except Exception as error:
        return dict(name=f['name'],status='failed',error=repr(error))
save()
with ThreadPoolExecutor(max_workers=4) as pool:
    for future in as_completed([pool.submit(fetch,f) for f in files.values()]):
        report['results'].append(future.result());save()
report['status']='resolved_sources_downloaded' if all(r['status']=='verified' for r in report['results']) else 'download_incomplete'
save()
print(json.dumps({k:report[k] for k in ('status','expected_files','expected_bytes','unresolved_packages')}))
