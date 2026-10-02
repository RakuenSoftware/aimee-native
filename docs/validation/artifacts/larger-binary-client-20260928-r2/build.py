from pathlib import Path
import subprocess,json,hashlib
root=Path(__file__).parent
with (root/'image-build.log').open('w') as log:
 r=subprocess.run(['podman','build','--network','none','--pull=never','--iidfile',str(root/'image.id'),'-f',str(root/'Containerfile'),str(root)],stdout=log,stderr=subprocess.STDOUT)
if r.returncode:
 (root/'build-error.json').write_text(json.dumps({'exit_code':r.returncode}));raise SystemExit(r.returncode)
w=next((root/'wheels').glob('*.whl'));m=root/'kernels/manifest.json'
(root/'build.json').write_text(json.dumps({'status':'built','scope':'Binary candidate; real packaged validation pending','image':(root/'image.id').read_text().strip(),'kernel_profiles':len(json.loads(m.read_text())['kernels']),'wheel_sha256':hashlib.sha256(w.read_bytes()).hexdigest(),'kernel_manifest_sha256':hashlib.sha256(m.read_bytes()).hexdigest()},indent=2)+'\n')
