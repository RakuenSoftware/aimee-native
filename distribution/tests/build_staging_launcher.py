"""Operator-only normal-edition launcher with a separate validation channel."""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess

p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--origin-root',required=True);p.add_argument('--output',required=True);p.add_argument('--target',required=True);a=p.parse_args()
source=pathlib.Path(a.source);origin=pathlib.Path(a.origin_root);output=pathlib.Path(a.output);output.mkdir(exist_ok=False)
identity=json.loads((origin/'identity.json').read_text())
url=identity['origin'].rstrip('/')+'/validation/sequence6'
env=dict(os.environ,AIMEE_RELEASE_PUBLIC_KEY=identity['release_public_key'],AIMEE_RELEASE_URL=url,AIMEE_RELEASE_CA_PEM=(origin/'ca.pem').read_text(),CARGO_TARGET_DIR=a.target,CARGO_BUILD_JOBS='2')
manifest=source/'distribution/launcher/Cargo.toml'
with (output/'build.log').open('w') as log:
    subprocess.run(['/root/.cargo/bin/cargo','build','--locked','--release','--manifest-path',str(manifest)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
binary=output/'aimee-native-staging';shutil.copy2(pathlib.Path(a.target)/'release/aimee-native',binary)
files=[manifest,manifest.with_name('Cargo.lock')]+sorted((manifest.parent/'src').glob('*.rs'))
report={'status':'built','edition':'normal (no lab-release feature)','validation_origin':url,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'source_sha256':{str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'scope':'Same normal launcher source, release key and CA; validation URL differs from the published channel. GPU runtime probes use the separately built normal production-URL launcher.'}
(output/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
