import os,json
from pathlib import Path
base=Path('/opt/aimee-auth-native-20260920');root=Path('/opt/aimee-qwen-adapter');rows=[]
for label,path,flags in [
 ('cannot modify image',base/'image/CURRENT',os.O_WRONLY),
 ('cannot modify authorization',base/'authorization.json',os.O_WRONLY),
 ('cannot read issuer private key',base/'private/issuer.key',os.O_RDONLY),
 ('cannot read authority credentials',root/'private/remote.conf',os.O_RDONLY),
 ('cannot read broader source image',root/'local-first-image/CURRENT',os.O_RDONLY),
 ('cannot read old model traces',root/'local-first-traces',os.O_RDONLY),
]:
 try:fd=os.open(path,flags);os.close(fd);denied=False
 except PermissionError:denied=True
 rows.append({'case':label,'pass':denied})
with (base/'image/CURRENT').open() as f:json.load(f)
rows.append({'case':'can read own authorized image','pass':True})
print(json.dumps({'uid':os.getuid(),'checks':rows,'all_pass':all(r['pass'] for r in rows)},indent=2))
