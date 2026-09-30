#!/usr/bin/env python3
"""Publish the tested plugin wheel on the existing controlled origin; no runtime image."""
from pathlib import Path
import hashlib,json,shutil,ssl,subprocess,tempfile,urllib.request,zipfile
root=Path('/opt/aimee-large-release-validation/portable-20260930')
for name in ['gemma26-live','gemma12-live','qwen27-live','installed-gpu-numerical','installed-activation','installed-activation-repeat','cross-compile-profiles','native-linkage']:
    report=json.loads((root/(name+'.json')).read_text())
    assert report['status']=='passed',name
    if 'answers' in report:assert len(report['answers'])==2 and all(x['passed'] for x in report['answers'])
wheel=next((root/'release-r2').glob('*.whl'))
audit=json.loads((root/'r2-wheel-audit.json').read_text());assert audit['status']=='passed'
assert hashlib.sha256(wheel.read_bytes()).hexdigest()==audit['sha256']
dep=json.loads((root/'gguf/dependency.json').read_text())
origin=Path('/opt/aimee-native-release');dest=origin/'www/plugins/portable/0.2.0'
dest.mkdir(parents=True,exist_ok=False);shutil.copyfile(wheel,dest/wheel.name)
base='https://192.168.0.126:8445/plugins/portable/0.2.0/'
dep['url']=base+dep['file']
assert hashlib.sha256((root/'gguf'/dep['file']).read_bytes()).hexdigest()==dep['sha256']
shutil.copyfile(root/'gguf'/dep['file'],dest/dep['file'])
manifest={'version':'0.2.0','scope':'Controlled standalone vLLM plugin preview; user supplies supported vLLM and model files.','wheel':wheel.name,'url':base+wheel.name,'sha256':audit['sha256'],'bytes':audit['bytes'],'compatibility':audit['compatibility'],'gguf_dependency':dep,'models':['Gemma4 12B','Gemma4 26B','Qwen3.8 27B'],'private_encoder_source_included':False,'generic_triton_kernel_source_included':True,'executed_gpu_architectures':['gfx1100'],'compilation_only_architectures':['sm80','sm89','sm90','sm120','gfx942','gfx1201'],'public_bootstrap_source_included':True,'runtime_image_included':False}
(dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for p in [dest/wheel.name,dest/dep['file'],dest/'manifest.json']:
    subprocess.run(['openssl','pkeyutl','-sign','-inkey',str(origin/'private/release.key'),'-rawin','-in',str(p),'-out',str(p)+'.sig'],check=True,capture_output=True)
ctx=ssl.create_default_context(cafile=str(origin/'ca.pem'))
with tempfile.TemporaryDirectory() as tmp:
    tmp=Path(tmp);key=tmp/'public.der'
    public=(origin/'release-public.hex').read_text().strip()
    assert public=='5d14ca247841adcc1130a4d95b82ead12ba699c03f2ba45f2f47524abde0c6c2'
    key.write_bytes(bytes.fromhex('302a300506032b6570032100'+public))
    for name in [wheel.name,dep['file'],'manifest.json']:
        with urllib.request.urlopen(base+name,context=ctx,timeout=60) as response:data=response.read()
        assert data==(dest/name).read_bytes()
        (tmp/name).write_bytes(data)
        with urllib.request.urlopen(base+name+'.sig',context=ctx,timeout=60) as response:(tmp/(name+'.sig')).write_bytes(response.read())
        subprocess.run(['openssl','pkeyutl','-verify','-pubin','-keyform','DER','-inkey',str(key),'-rawin','-in',str(tmp/name),'-sigfile',str(tmp/(name+'.sig'))],capture_output=True,check=True)
    with urllib.request.urlopen(dep['url'],context=ctx,timeout=60) as response:data=response.read()
    assert len(data)==dep['bytes'] and hashlib.sha256(data).hexdigest()==dep['sha256']
report={'status':'passed','scope':'Full TLS downloads and pinned Ed25519 verification of plugin and manifest; dependency size/hash verification.','manifest':manifest,'manifest_sha256':hashlib.sha256((dest/'manifest.json').read_bytes()).hexdigest(),'public_key':public}
(root/'published-delivery.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'url':manifest['url'],'sha256':audit['sha256']}))
