#!/usr/bin/env python3
"""Resolve the published extra with the already installed runtime, without mutation."""
from pathlib import Path
import hashlib,json,shutil,subprocess
r=Path('/opt/aimee-large-release-validation/portable-20260930')
publication=json.loads((r/'published-delivery.json').read_text())
assert publication['status']=='passed'
ca=r/'release-ca.pem'
shutil.copyfile('/opt/aimee-native-release/ca.pem',ca)
wheel=next((r/'release-r2').glob('*.whl'))
plan=r/'pip-extra-plan.json'
command=['podman','exec','aimee-plugin-portable-test','python3','-m','pip','install','--dry-run','--no-index','--cert',str(ca),'--report',str(plan),str(wheel)+'[gguf]']
result=subprocess.run(command,capture_output=True,text=True)
(r/'pip-extra.log').write_text(result.stdout+result.stderr)
assert result.returncode==0,(result.returncode,result.stderr)
p=json.loads(plan.read_text())
dep=publication['manifest']['gguf_dependency']
# A fully installed environment legitimately has an empty installation plan.
# Check resolution separately from fetching and hashing the pinned dependency.
import zipfile
with zipfile.ZipFile(wheel) as z:
    metadata=z.read(next(n for n in z.namelist() if n.endswith('.dist-info/METADATA'))).decode()
assert dep['url']+'#sha256='+dep['sha256'] in metadata
download=r/'pip-download';download.mkdir(exist_ok=True)
fetch=subprocess.run(['podman','exec','aimee-plugin-portable-test','python3','-m','pip','download','--no-index','--no-deps','--cert',str(ca),'--dest',str(download),dep['url']+'#sha256='+dep['sha256']],capture_output=True,text=True)
with (r/'pip-extra.log').open('a') as log:log.write(fetch.stdout+fetch.stderr)
assert fetch.returncode==0,fetch.stderr
assert hashlib.sha256((download/dep['file']).read_bytes()).hexdigest()==dep['sha256']
report={'status':'passed','scope':__doc__,'mutated_runtime':False,'plugin_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),'dependency_url':dep['url'],'dependency_sha256':dep['sha256'],'pip_resolved_installations':[{'name':v['metadata']['name'],'version':v['metadata']['version']} for v in p['install']]}
(r/'pip-extra-delivery.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
