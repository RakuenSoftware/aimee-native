"""Prepare a disposable NAS-backed canonical store from pinned built artifacts.

Generated boot runs only in a private mount/network namespace. Original build
images are read-only; migration admin and runtime identities remain separate.
"""
import argparse,hashlib,json
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();root=a.root
assert str(root).startswith('/mnt/pve/backup/aimee-experiments/retained-transfer-20261011-r1/')
old=Path('/mnt/pve/backup/aimee-experiments/turn-scoped-learning-20261010-r1')
template=old/'learning-runtime-readiness-r5/learning_runtime_readiness.py'
s=template.read_text()
s=s.replace('campaign = root.parent',f'campaign = Path({str(old)!r})')
s=s.replace("short = Path('/mnt/pve/backup/aimee-lrn-ready-r' + run_suffix)","short = Path('/run/retained-study-store')")
s=s.replace("    short.mkdir()", "    subprocess.run(['mount', '--make-rprivate', '/'], check=True)\n    short.mkdir()")
s=s.replace("    script = short / 'readiness-harness.sh'", '''    # Retain the deployed-service startup and liveness checks, then expose
    # the owner socket. Omit the deterministic learning fixtures entirely.
    harness = harness.replace('deploy server learning "$SRVHOME"', 'deploy server learning "$SRVHOME"'+chr(10)+'deploy server memory "$SRVHOME"')
    harness = harness.replace('for m in config postgres aimee learning; do attach', 'for m in config postgres aimee learning memory; do attach')
    harness = harness.split('reset_learning_state() {', 1)[0]
    harness += r"""
python3 - <<'READY'
import datetime, json, os
from pathlib import Path
study=Path(os.environ['LINKED_STUDY_ROOT'])
parent=os.getppid()
# The namespace controller is the parent of this shell, not this helper.
controller=int(os.environ['LINKED_NAMESPACE_PID'])
sock='/proc/'+str(controller)+'/root'+os.environ['AIMEE_API_ENDPOINT'][5:]
receipt={'private_experiment_instance':True,'study':'retained-transfer-20261011-r1',
         'data_root':os.environ['LINKED_STORE_INSTANCE'],'http_socket':sock,
         'namespace_controller_pid':controller,'source_commit':os.environ['STUDY_COMMIT'],
         'storage':'Dedicated NAS workspace.ext4; private mount and loopback network',
         'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
with (study/('canonical-store-ready-'+os.environ['LINKED_STORE_REVISION']+'.json')).open('x') as out:json.dump(receipt,out,indent=2)
READY
while [ ! -f "$LINKED_STORE_INSTANCE/stop" ]; do sleep 2; done
"""
    env.update(LINKED_STUDY_ROOT=str(root.parent), LINKED_NAMESPACE_PID=str(os.getpid()), LINKED_STORE_INSTANCE=str(root), LINKED_STORE_REVISION='r'+run_suffix)
    script = short / 'readiness-harness.sh' ''')
s=s.replace('child.wait(timeout=600)','child.wait(timeout=43200)')
s=s.replace("receipt['passed'] = receipt['exit_code'] == 0 and receipt.get('harness-failed.txt') == 0", "receipt['passed'] = receipt['exit_code'] == 0\n    receipt['scope'] = 'Isolated canonical store lifecycle; no learning efficacy or native result'\n    (root.parent / 'canonical-store-stopped.json').write_text(json.dumps({'namespace_pid': os.getpid(), 'exit_code': receipt['exit_code']}))")
root.mkdir(parents=True,exist_ok=False)
(root/'boot.py').write_text(s)
(root/'boot-freeze.json').write_text(json.dumps({'template_path':str(template),'template_sha256':hashlib.sha256(template.read_bytes()).hexdigest(),
    'boot_sha256':hashlib.sha256(s.encode()).hexdigest(),'core_source_commit':'750e34295970889c88428b44b93ff2d61c5462b3',
    'scope':'Owner provisioning of a separate disposable instance; existing fixture grants, no runtime DDL/bypass authority'},indent=2)+'\n')
compile(s,str(root/'boot.py'),'exec')
print(root/'boot.py')
