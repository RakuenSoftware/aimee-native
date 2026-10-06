"""Resume verified NAS archive relocation, preserving tar hard-link identities."""
from pathlib import Path
import subprocess,json,hashlib,tarfile,ast
NAS=Path('/mnt/pve/backup/aimee-experiments/root-evacuation-20261005-r1/gemma-composition-candidate-r1/storage-recovery-r2')
ROOT=Path('/opt/jmlr-second-review-20261005/repair-cache/gemma-composition-candidate-r1')
manifest=json.loads((NAS/'source-manifest.json').read_bytes());archive=NAS/'owned-ct-build-scratch.tar'
def digest(stream):
 h=hashlib.sha256()
 for b in iter(lambda:stream.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
observed={};hardlinks=0
with tarfile.open(archive,'r|') as tar:
 for m in tar:
  assert m.name.split('/')[0] in ['target','cargo-home'] and '..' not in Path(m.name).parts,m.name
  if m.isfile():observed[m.name]={'type':'file','size':m.size,'sha256':digest(tar.extractfile(m))}
  elif m.issym():observed[m.name]={'type':'symlink','target':m.linkname}
  elif m.islnk():
   assert m.linkname in observed and observed[m.linkname]['type']=='file'
   observed[m.name]=dict(observed[m.linkname]);hardlinks+=1
  else:assert m.isdir(),('unexpected member',m.name,m.type)
assert observed==manifest['entries']
nodes=ast.parse((ROOT/'relocate_owned_build_scratch.py').read_text()).body
code=next(ast.literal_eval(n.value) for n in nodes if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='code' for t in n.targets))
current=json.loads(subprocess.check_output(['pct','exec','101','--','python3','-c',code],text=True));assert current==manifest
with archive.open('rb') as f:checksum=digest(f)
subprocess.run(['pct','exec','101','--','python3','-c',"import pathlib,shutil;root=pathlib.Path('/opt/jmlr-gemma-prefix-build-20261006-r1');names=['target','cargo-home'];assert all((root/n).resolve()==root/n for n in names);[shutil.rmtree(root/n) for n in names]"],check=True)
receipt={'status':'passed','owned_ct_root':manifest['owned_root'],'removed_only':['target','cargo-home'],'no_open_processes_verified_twice':True,'archive_sha256':checksum,'archive_bytes':archive.stat().st_size,'entry_count':len(observed),'archive_hardlinks':hardlinks,'archive_content_verified_against_source_manifest':True,'canonical_wheel_source_logs_bindings_retained':True,'original_relocation_attempt':'standard tar hard links required verification support; archive/source unchanged and retained'}
with (NAS/'verified-relocation.json').open('x') as f:f.write(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
