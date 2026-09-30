#!/usr/bin/env python3
"""Publish the tested 0.2.1 correction on the existing private release origin."""
from pathlib import Path
import hashlib
import json
import shutil
import ssl
import subprocess
import tempfile
import urllib.request

root = Path('/opt/aimee-large-release-validation/no-memory-20260930')
live = json.loads((root/'live.json').read_text())
assert live['status'] == 'passed' and live['consumer_from_wheel']
assert live['environment']['aimee-vllm'] == '0.2.1'
assert live['empty_first']['passed'] and live['recovery']['passed']
for name in ['answers', 'interleaved_tasks']:
    assert len(live[name]) == 24 and all(x['passed'] for x in live[name])
assert json.loads((root/'api-checks.json').read_text())['status'] == 'passed'
wheel = next((root/'release').glob('*.whl'))
audit = json.loads((root/'wheel-audit.json').read_text())
assert audit['status'] == 'passed'
assert hashlib.sha256(wheel.read_bytes()).hexdigest() == audit['sha256']
origin = Path('/opt/aimee-native-release')
dest = origin/'www/plugins/portable/0.2.1'
dest.mkdir(parents=True, exist_ok=False)
shutil.copyfile(wheel, dest/wheel.name)
base = 'https://192.168.0.126:8445/plugins/portable/0.2.1/'
manifest = {
    'version': '0.2.1', 'wheel': wheel.name, 'url': base+wheel.name,
    'sha256': audit['sha256'], 'bytes': audit['bytes'],
    'compatibility': audit['compatibility'],
    'scope': 'Authorized empty-memory selections; private preview. Live validation: Gemma4 12B Q8_0 on RTX 5080.',
    'live_validation': {'native_recall': 24, 'empty_interleaved': 24, 'empty_cold_start': True, 'interrupted_stream_recovery': True},
    'native_library_sha256': audit['native_library_sha256'],
    'native_library_changed_from_0_2_0': False,
    'requires': 'Updated hosted preparation and native-publication service for explicit no_memory responses.',
    'private_encoder_source_included': False, 'runtime_image_included': False,
}
(dest/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
for path in [dest/wheel.name, dest/'manifest.json']:
    subprocess.run(['openssl','pkeyutl','-sign','-inkey',str(origin/'private/release.key'),'-rawin','-in',str(path),'-out',str(path)+'.sig'], check=True, capture_output=True)
ctx = ssl.create_default_context(cafile=str(origin/'ca.pem'))
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    public = (origin/'release-public.hex').read_text().strip()
    assert public == '5d14ca247841adcc1130a4d95b82ead12ba699c03f2ba45f2f47524abde0c6c2'
    key = tmp/'public.der'; key.write_bytes(bytes.fromhex('302a300506032b6570032100'+public))
    for name in [wheel.name, 'manifest.json']:
        with urllib.request.urlopen(base+name, context=ctx, timeout=60) as response: data=response.read()
        assert data == (dest/name).read_bytes()
        (tmp/name).write_bytes(data)
        with urllib.request.urlopen(base+name+'.sig', context=ctx, timeout=60) as response: (tmp/(name+'.sig')).write_bytes(response.read())
        subprocess.run(['openssl','pkeyutl','-verify','-pubin','-keyform','DER','-inkey',str(key),'-rawin','-in',str(tmp/name),'-sigfile',str(tmp/(name+'.sig'))], check=True, capture_output=True)
(root/'delivery/published.json').write_text(json.dumps({'status':'passed','manifest':manifest,'tls_download_and_signature_verified':True},indent=2)+'\n')
print(json.dumps({'status':'passed','url':manifest['url'],'sha256':manifest['sha256']}))
