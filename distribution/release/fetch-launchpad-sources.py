"""Collect exact publication source files and check DSC identity/SHA-256 entries.

DSC files are retrieved over HTTPS from recorded Launchpad publication URLs.
Their OpenPGP signatures are retained, not verified by this collector. No source
is unpacked or executed; this is not full redistribution approval.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import shutil
import urllib.parse
import urllib.request

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--plan',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();a.output.mkdir(exist_ok=False)
if shutil.disk_usage(a.output).free < 12*1024**3:raise RuntimeError('insufficient storage reserve')
plan=json.loads(a.plan.read_text())
report=dict(status='downloading',scope=__doc__,plan_sha256=hashlib.sha256(a.plan.read_bytes()).hexdigest(),results=[])
def save():
 temp=a.output/'report.tmp';temp.write_text(json.dumps(report,indent=2)+'\n');temp.replace(a.output/'report.json')
def download(url,destination,maximum):
 assert urllib.parse.urlsplit(url).scheme=='https' and urllib.parse.urlsplit(url).hostname=='launchpad.net'
 partial=destination.with_name(destination.name+'.partial');size=0;sha=hashlib.sha256()
 with urllib.request.urlopen(url,timeout=60) as response,partial.open('xb') as out:
  while chunk:=response.read(1024**2):
   size+=len(chunk)
   if size>maximum:raise ValueError('source file exceeds size bound')
   sha.update(chunk);out.write(chunk)
 partial.rename(destination)
 return dict(name=destination.name,bytes=size,sha256=sha.hexdigest(),url=url)
def fetch(row):
 result=dict(source=row['source'],version=row['version'],publication=row['publication'],files=[])
 try:
  assert Path(row['source']).name==row['source']
  out=a.output/row['source'];out.mkdir()
  urls={urllib.parse.unquote(urllib.parse.urlsplit(u).path.rsplit('/',1)[-1]):u for u in row['files']}
  assert all(Path(name).name==name for name in urls)
  dscs=[n for n in urls if n.endswith('.dsc')];assert len(dscs)==1
  name=dscs[0];record=download(urls[name],out/name,4*1024**2);record['verification']='HTTPS publication retrieval; signature unverified';result['files'].append(record)
  fields={};key=None
  for line in (out/name).read_text().splitlines():
   if line.startswith('-----BEGIN PGP SIGNATURE'):break
   if line.startswith(' ') and key:fields[key]+='\n'+line.strip()
   elif ': ' in line:key,value=line.split(': ',1);fields[key]=value
   else:key=None
  assert fields['Source']==row['source'] and fields['Version']==row['version']
  checks={}
  for line in fields.get('Checksums-Sha256','').splitlines():
   if line.strip():
    digest,size,filename=line.split();checks[filename]=(digest,int(size))
  # A field can have an empty first line after its colon.
  if not checks:
   lines=(out/name).read_text().splitlines();start=lines.index('Checksums-Sha256:')+1
   for line in lines[start:]:
    if not line.startswith(' '):break
    digest,size,filename=line.split();checks[filename]=(digest,int(size))
  assert checks
  for filename,(digest,size) in checks.items():
   assert filename in urls and Path(filename).name==filename
   item=download(urls[filename],out/filename,size)
   assert item['bytes']==size and item['sha256']==digest
   item['verification']='matched DSC SHA-256';result['files'].append(item)
  result['status']='identity_and_file_checksums_matched'
 except Exception as error:result.update(status='failed',error=repr(error))
 return result
save()
with ThreadPoolExecutor(max_workers=3) as pool:
 futures=[pool.submit(fetch,row) for row in plan['results'] if row['status']=='publication_located']
 for future in as_completed(futures):report['results'].append(future.result());save()
report['status']='collected' if all(r['status']=='identity_and_file_checksums_matched' for r in report['results']) else 'incomplete'
save();print(json.dumps({k:report[k] for k in ['status']}))
