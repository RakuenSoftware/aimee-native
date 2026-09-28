import subprocess,json,hashlib
from pathlib import Path
repo=Path('/tmp/aimee-native-precomputed')
code="""from pathlib import Path
import hashlib,json
r=Path('/opt/aimee-memory-lab/larger-binary-client-20260928/distribution')
print(json.dumps({str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in r.rglob('*') if p.is_file() and p.suffix in ('.py','.toml','.rs','.h','.c','.sh') and '__pycache__' not in p.parts and 'target' not in p.parts},sort_keys=True))
"""
remote=json.loads(subprocess.check_output(['python3','/tmp/aimee-ct101.py'],input=code,text=True))
revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
rows=[]
for name,digest in remote.items():
 p='distribution/'+name
 committed=subprocess.run(['git','show',revision+':'+p],cwd=repo,capture_output=True)
 h=hashlib.sha256(committed.stdout).hexdigest() if committed.returncode==0 else None
 rows.append({'path':p,'build_directory_sha256':digest,'committed_sha256':h,'matches':h==digest})
report={'scope':'Post-build source-directory comparison, not a build-time attestation or reproducible-build proof. Includes source files by listed extensions; does not cover base image, native library, compiled kernels or toolchain.','revision':revision,'matches':sum(r['matches'] for r in rows),'files':rows}
out=repo/'docs/validation/artifacts/larger-build-source-comparison-20260928'
out.mkdir(exist_ok=False)
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
(out/'audit.py').write_bytes(Path(__file__).read_bytes())
(out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(out.iterdir()) if p.is_file()))
print(json.dumps(report,indent=2))
