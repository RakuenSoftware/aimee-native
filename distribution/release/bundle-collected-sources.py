"""Assemble the collected portion of third-party sources; never claim completeness."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--root',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
if a.output.exists() or a.output.with_suffix('.partial').exists():raise FileExistsError(a.output)
entries=[]
reports={}
for folder in ['os-source-download-r1','launchpad-source-download-r2','launchpad-source-download-r3']:
 data=json.loads((a.root/folder/'report.json').read_text());reports[folder]=data
 if folder=='os-source-download-r1':
  assert data['status']=='resolved_sources_downloaded'
  for row in data['results']:
   assert row['status']=='verified'
   entries.append((a.root/folder/row['name'],'ubuntu/'+row['name'],row['sha256'],row['bytes']))
 else:
  for row in data['results']:
   if row['status']!='identity_and_file_checksums_matched':continue
   for f in row['files']:
    entries.append((a.root/folder/row['source']/f['name'],'historical/'+row['source']+'/'+f['name'],f['sha256'],f['bytes']))
if shutil.disk_usage(a.output.parent).free < sum(x[3] for x in entries)+8*1024**3:raise RuntimeError('storage reserve unavailable')
class CheckedReader:
 def __init__(self,file):self.file=file;self.sha=hashlib.sha256()
 def read(self,size=-1):
  data=self.file.read(size);self.sha.update(data);return data
partial=a.output.with_suffix('.partial')
with tarfile.open(partial,'w') as archive:
 for path,name,digest,size in entries:
  assert path.is_file() and not path.is_symlink() and path.stat().st_size==size
  info=tarfile.TarInfo(name);info.size=size;info.mode=0o644
  with path.open('rb') as stream:
   reader=CheckedReader(stream);archive.addfile(info,reader)
   if reader.sha.hexdigest()!=digest:raise ValueError('source changed: '+name)
 for name,data in reports.items():
  raw=(json.dumps(data,indent=2)+'\n').encode();info=tarfile.TarInfo('manifests/'+name+'.json');info.size=len(raw);archive.addfile(info,io.BytesIO(raw))
 raw=b'PARTIAL THIRD-PARTY SOURCE COLLECTION\n263 of 342 installed OS source-package/version pairs collected.\n79 pairs and other component source/notice obligations remain unresolved.\nHistorical DSC signatures are retained but not independently verified.\nThis is not a release or redistribution approval. No private Aimee implementation is included.\n'
 info=tarfile.TarInfo('README.txt');info.size=len(raw);archive.addfile(info,io.BytesIO(raw))
partial.rename(a.output)
with a.output.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
report=dict(status='partial_bundle_assembled',file=a.output.name,bytes=a.output.stat().st_size,sha256=digest,source_files=len(entries),source_bytes=sum(x[3] for x in entries),remaining_source_version_pairs=79,redistribution_approved=False)
a.output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
