#!/usr/bin/env python3
"""Append signed hardware evidence without modifying the immutable release manifest.

Run in CT101; the host must provision the campaign delivery/ directory writable
by CT101 for the verified report copies. Input reports remain host-owned.
"""
from pathlib import Path
import hashlib,json,ssl,subprocess,tempfile,urllib.request
r=Path('/opt/aimee-large-release-validation/cuda-5080-20260930')
def read(name):
    x=json.loads((r/(name+'.json')).read_text());assert x['status']=='passed',name;return x
env=read('environment');numerical=read('numerical');live=read('gemma12-live')
activations=[read('activation'),read('activation-repeat')]
assert env['wheel_sha256']=='511a16373291774b85d427468f484fedc531310465c25ee55d22fa79ec99ce37'
assert env['identical_installed_plugin_files']==21
assert numerical['gpu']=='NVIDIA GeForce RTX 5080' and numerical['arch']=='(12, 0)'
assert all(c['bit_exact'] for a in activations for c in a['cases'])
count=sum(len(c['activation_us']) for a in activations for c in a['cases']);assert count==216
assert len(live['answers'])==2 and all(a['passed'] for a in live['answers'])
assert live['authenticated_connect'] and live['consumer_from_wheel']
record={'status':'passed','wheel_sha256':env['wheel_sha256'],'environment':env,
        'numerical':numerical,'bit_exact_activations':count,'live_model':'Gemma4 12B',
        'live_answers':live['answers'],'model_files':read('model-files')['files'],
        'scope':'Physical execution on one RTX 5080. TP=2 memory shards were tested sequentially; no multi-GPU NVIDIA execution or Intel claim.',
        'runtime_setting':'VLLM_USE_FLASHINFER_SAMPLER=0 selects upstream PyTorch sampling in this pip-only environment.'}
origin=Path('/opt/aimee-native-release');name='cuda-5080-20260930.json'
dest=origin/'www/plugins/portable/0.2.0/validation';dest.mkdir(exist_ok=True)
p=dest/name
serialized=(json.dumps(record,indent=2)+'\n').encode()
if p.exists():assert p.read_bytes()==serialized, 'Immutable validation record differs'
else:
    with p.open('xb') as f:f.write(serialized)
subprocess.run(['openssl','pkeyutl','-sign','-inkey',str(origin/'private/release.key'),'-rawin','-in',str(p),'-out',str(p)+'.sig'],check=True,capture_output=True)
url='https://192.168.0.126:8445/plugins/portable/0.2.0/validation/'+name
ctx=ssl.create_default_context(cafile=str(origin/'ca.pem'))
data=urllib.request.urlopen(url,context=ctx,timeout=30).read();assert data==p.read_bytes()
sig=urllib.request.urlopen(url+'.sig',context=ctx,timeout=30).read()
public=(origin/'release-public.hex').read_text().strip()
assert public=='5d14ca247841adcc1130a4d95b82ead12ba699c03f2ba45f2f47524abde0c6c2'
with tempfile.TemporaryDirectory() as tmp:
    tmp=Path(tmp);(tmp/'key.der').write_bytes(bytes.fromhex('302a300506032b6570032100'+public));(tmp/'record').write_bytes(data);(tmp/'signature').write_bytes(sig)
    subprocess.run(['openssl','pkeyutl','-verify','-pubin','-keyform','DER','-inkey',str(tmp/'key.der'),'-rawin','-in',str(tmp/'record'),'-sigfile',str(tmp/'signature')],check=True,capture_output=True)
(r/'delivery/signed-validation.json').write_bytes(data)
(r/'delivery/validation-delivery.json').write_text(json.dumps({'status':'passed','url':url,'sha256':hashlib.sha256(data).hexdigest(),'public_key':public,'scope':'Full TLS download and pinned Ed25519 verification; original release manifest unchanged.'},indent=2)+'\n')
print(url)
