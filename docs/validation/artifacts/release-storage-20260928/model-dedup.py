import pathlib,json,hashlib,os,time,stat
r=pathlib.Path('/opt/aimee-native-release/www'); paths=sorted(r.rglob('models/model.gguf'));entries=[];groups={}
out=pathlib.Path('/opt/aimee-native-release/model-dedup-20260928.json');assert not out.exists()
for p in paths:
 s=p.stat();manifest=json.loads((p.parent.parent/'manifest.json').read_text());a=next(x for x in manifest['artifacts'] if x['path']=='models/model.gguf');assert s.st_size==a['bytes'];key=(s.st_dev,s.st_ino)
 if key not in groups:
  with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
  assert h==a['sha256'],str(p);groups[key]=(p,h,s)
 else:assert groups[key][1]==a['sha256']
 entries.append({'path':str(p),'bytes':s.st_size,'sha256':a['sha256'],'old_inode':s.st_ino,'mode':stat.S_IMODE(s.st_mode)})
by_content={};replaced=[]
for (dev,ino),(p,h,s) in groups.items():
 identity=(dev,h,s.st_size,stat.S_IMODE(s.st_mode),s.st_uid,s.st_gid)
 canonical=by_content.setdefault(identity,p)
 if canonical==p:continue
 for e in entries:
  if e['old_inode']!=ino:continue
  q=pathlib.Path(e['path']);assert q.stat().st_ino==ino
  tmp=q.with_name(q.name+'.dedup-stage');assert not tmp.exists();os.link(canonical,tmp);os.replace(tmp,q);replaced.append(str(q))
for e in entries:
 p=pathlib.Path(e['path']);s=p.stat();e['new_inode']=s.st_ino;assert s.st_size==e['bytes'] and stat.S_IMODE(s.st_mode)==e['mode']
report={'status':'passed','time':time.time(),'scope':'SHA-256 verified identical immutable model files hard-linked; manifests, signatures and every release path retained. No memory bank or running study changed.','unique_inodes_before':len(groups),'unique_inodes_after':len(set(e['new_inode'] for e in entries)),'logically_reclaimed_bytes':sum(v[2].st_size for v in groups.values())-sum(identity[2] for identity in by_content),'files':entries,'replaced_paths':replaced}
out.write_text(json.dumps(report,indent=2)+chr(10));print(json.dumps({k:v for k,v in report.items() if k not in ['files','replaced_paths']}))
