"""Archive/verify only this candidate's transient CT101 build scratch."""
from pathlib import Path
import subprocess,json,hashlib,tarfile,shutil
NAS=Path('/mnt/pve/backup/aimee-experiments/root-evacuation-20261005-r1/gemma-composition-candidate-r1/storage-recovery-r2')
TASK='/opt/jmlr-gemma-prefix-build-20261006-r1'
NAS.mkdir(mode=0o700,exist_ok=False)
def digest_stream(stream):
 h=hashlib.sha256()
 for b in iter(lambda:stream.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def ct(code):return subprocess.check_output(['pct','exec','101','--','python3','-c',code],text=True)
code='''
import os,json,hashlib
from pathlib import Path
root=Path('/opt/jmlr-gemma-prefix-build-20261006-r1');names=['target','cargo-home']
for n in names:assert (root/n).resolve()==root/n and (root/n).is_dir()
open_processes=[]
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 for fd in (proc/'fd').glob('*'):
  try:
   link=os.readlink(fd)
   if any(link.startswith(str(root/n)+'/') for n in names):open_processes.append(int(proc.name))
  except OSError:pass
assert not open_processes,open_processes
result={}
for n in names:
 for p in (root/n).rglob('*'):
  key=str(p.relative_to(root))
  if p.is_symlink():result[key]={'type':'symlink','target':os.readlink(p)}
  elif p.is_file():
   h=hashlib.sha256()
   with p.open('rb') as f:
    for b in iter(lambda:f.read(8388608),b''):h.update(b)
   result[key]={'type':'file','size':p.stat().st_size,'sha256':h.hexdigest()}
print(json.dumps({'owned_root':str(root),'no_open_processes':True,'entries':result},sort_keys=True))
'''
manifest=json.loads(ct(code));(NAS/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
archive=NAS/'owned-ct-build-scratch.tar'
with archive.open('xb') as f:subprocess.run(['pct','exec','101','--','tar','--one-file-system','-cf','-','-C',TASK,'target','cargo-home'],stdout=f,check=True)
observed={}
with tarfile.open(archive,'r|') as tar:
 for m in tar:
  assert m.name.split('/')[0] in ('target','cargo-home') and '..' not in Path(m.name).parts,m.name
  if m.isfile():
   stream=tar.extractfile(m);observed[m.name]={'type':'file','size':m.size,'sha256':digest_stream(stream)}
  elif m.issym():observed[m.name]={'type':'symlink','target':m.linkname}
  else:assert m.isdir(),('unexpected archive member',m.name,m.type)
assert observed==manifest['entries'],'archive contents differ from owned source'
assert json.loads(ct(code))==manifest,'source changed or process opened scratch during archive'
with archive.open('rb') as f:checksum=digest_stream(f)
# Remove only precisely verified task-owned roots; no symlink-following cleanup.
ct("import pathlib,shutil;root=pathlib.Path('/opt/jmlr-gemma-prefix-build-20261006-r1');names=['target','cargo-home'];assert all((root/n).resolve()==root/n for n in names);[shutil.rmtree(root/n) for n in names]")
receipt={'status':'passed','owned_ct_root':TASK,'removed_only':['target','cargo-home'],'no_open_processes_verified_twice':True,'archive_sha256':checksum,'archive_bytes':archive.stat().st_size,'entry_count':len(observed),'archive_content_verified_against_source_manifest':True,'canonical_wheel_source_logs_bindings_retained':True}
with (NAS/'verified-relocation.json').open('x') as f:f.write(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
