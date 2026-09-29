#!/usr/bin/env python3
"""Publish the tested plugin wheel on the existing controlled origin; no runtime image."""
from pathlib import Path
import hashlib,json,shutil,ssl,subprocess,tempfile,urllib.request,zipfile
root=Path('/opt/aimee-large-release-validation/plugin-standalone-20260929')
for name in ['gemma26-live','qwen27-live','gemma12-final-wheel','gemma12-recovery','wrong-model-binding']:
    report=json.loads((root/(name+'.json')).read_text())
    assert report['status']=='passed',name
    if 'answers' in report:assert len(report['answers'])==2 and all(x['passed'] for x in report['answers'])
assert json.loads((root/'gemma12-recovery.json').read_text())['recovery']['passed']
wheel=next((root/'release-final').glob('*.whl'))
audit=json.loads((root/'final-wheel-audit.json').read_text());assert audit['status']=='passed'
assert hashlib.sha256(wheel.read_bytes()).hexdigest()==audit['sha256']
with zipfile.ZipFile(next((root/'dist-final').glob('*.whl'))) as old,zipfile.ZipFile(wheel) as new:
    names=[n for n in old.namelist() if n.startswith('aimee_vllm/')]
    assert names==[n for n in new.namelist() if n.startswith('aimee_vllm/')]
    assert all(old.read(n)==new.read(n) for n in names)
(root/'published-component-equivalence.json').write_text(json.dumps({'status':'passed','final_wheel_sha256':audit['sha256'],'identical_plugin_code_and_native_assets':len(names),'scope':'All runtime assets match the three-model test wheel; only distribution version/dependency metadata changed.'},indent=2)+'\n')
dep=json.loads((root/'gguf-rocm-dependency.json').read_text())
origin=Path('/opt/aimee-native-release');dest=origin/'www/plugins/rocm723-gfx1100/0.1.1'
dest.mkdir(parents=True,exist_ok=False);shutil.copyfile(wheel,dest/wheel.name)
base='https://192.168.0.126:8445/plugins/rocm723-gfx1100/0.1.1/'
manifest={'version':'0.1.1','scope':'Controlled standalone vLLM plugin preview; user supplies supported vLLM and model files.','wheel':wheel.name,'url':base+wheel.name,'sha256':audit['sha256'],'bytes':audit['bytes'],'compatibility':audit['compatibility'],'gguf_dependency':dep,'models':['Gemma4 12B','Gemma4 26B','Qwen3.8 27B'],'private_implementation_source_included':False,'public_bootstrap_source_included':True,'runtime_image_included':False}
(dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for p in [dest/wheel.name,dest/'manifest.json']:
    subprocess.run(['openssl','pkeyutl','-sign','-inkey',str(origin/'private/release.key'),'-rawin','-in',str(p),'-out',str(p)+'.sig'],check=True,capture_output=True)
ctx=ssl.create_default_context(cafile=str(origin/'ca.pem'))
with tempfile.TemporaryDirectory() as tmp:
    tmp=Path(tmp);key=tmp/'public.der'
    public=(origin/'release-public.hex').read_text().strip()
    assert public=='5d14ca247841adcc1130a4d95b82ead12ba699c03f2ba45f2f47524abde0c6c2'
    key.write_bytes(bytes.fromhex('302a300506032b6570032100'+public))
    for name in [wheel.name,'manifest.json']:
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
