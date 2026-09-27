"""Operator-only release-6 preparation upgrade on the designated Proxmox host.

Run after the fixed learning campaign and image certification. No customer keys,
source records, or encoder implementation are placed in the client artifact.
"""
import json
import pathlib
import subprocess
import time

ROOT = pathlib.Path('/root/aimee-release-cert-20260927')
REPORT = ROOT / 'preparation-upgrade.json'

def ct_script(ct, source):
    return subprocess.check_output(['pct', 'exec', str(ct), '--', 'python3', '-'], input=source, text=True)

def service(*args):
    subprocess.run(['pct', 'exec', '101', '--', 'systemctl', *args], check=True)

state = json.loads(subprocess.check_output(['pct', 'exec', '113', '--', 'cat', '/opt/swe-native/source-learning-20260927/status.json']))
if state['status'] != 'complete':
    raise RuntimeError('learning must finish before compiler replacement')
report = {'status': 'incomplete', 'compute_dtype': 'float32', 'encoding_revision': 'native-negative-v2-fp32'}
backup_created = False
try:
    ct_script(101, '''import pathlib,shutil,json
r=pathlib.Path('/opt/aimee-native-compiler'); stage=pathlib.Path('/opt/aimee-memory-lab/release-candidate-20260927/preparation'); b=r/'release6-backup'
assert not b.exists(), 'existing backup requires operator inspection'
for name in ('gemma_compile.py','resident_compile.py'):compile((stage/name).read_text(),name,'exec')
assert json.loads((r/'resident.json').read_text()).get('compute_dtype','bfloat16')=='bfloat16'
b.mkdir(mode=0o700)
for name in ('gemma_compile.py','resident_compile.py','resident.json','worker.json','worker.oneshot.json'):shutil.copy2(r/name,b/name)
''')
    backup_created = True
    # Free both resident copies before loading the production FP32 copy.
    service('stop', 'aimee-native-compiler-diagnostic', 'aimee-native-compiler')
    ct_script(101, '''import pathlib,shutil,json,os
r=pathlib.Path('/opt/aimee-native-compiler'); stage=pathlib.Path('/opt/aimee-memory-lab/release-candidate-20260927/preparation')
def replace(p,data):
 st=p.stat(); q=p.with_suffix(p.suffix+'.release6');q.write_bytes(data);os.chmod(q,st.st_mode);os.chown(q,st.st_uid,st.st_gid);q.replace(p)
for name in ('gemma_compile.py','resident_compile.py'):replace(r/name,(stage/name).read_bytes())
p=r/'resident.json';d=json.loads(p.read_text());d['compute_dtype']='float32';replace(p,(json.dumps(d)+'\\n').encode())
for name in ('worker.json','worker.oneshot.json'):
 p=r/name;d=json.loads(p.read_text());assert '--compute-dtype' not in d['compiler'];d['compiler']+=['--compute-dtype','float32'];replace(p,(json.dumps(d)+'\\n').encode())
''')
    started = int(time.time())
    service('start', 'aimee-native-compiler')
    for _ in range(180):
        logs = subprocess.check_output(['pct','exec','101','--','journalctl','-u','aimee-native-compiler','--since','@'+str(started),'-o','cat','--no-pager'], text=True)
        if '"event": "ready"' in logs:
            break
        time.sleep(1)
    else:
        raise TimeoutError('upgraded resident compiler not ready')
    ct_script(100, '''import pathlib,json,shutil,os
p=pathlib.Path('/etc/aimee-native/preparation.json');d=json.loads(p.read_text());assert d['encoding_revision']=='native-negative-v1'
b=p.with_name('preparation.before-release6.json');assert not b.exists();shutil.copy2(p,b)
st=p.stat();d['encoding_revision']='native-negative-v2-fp32';q=p.with_suffix('.release6');q.write_text(json.dumps(d)+'\\n');os.chmod(q,st.st_mode);os.chown(q,st.st_uid,st.st_gid);q.replace(p)
''')
    # The preparer reads its config per request. No account/authority change.
    report['status'] = 'deployed_pending_client_validation'
except BaseException as error:
    report.update(status='failed', error=str(error))
    if backup_created:
        service('stop', 'aimee-native-compiler')
        ct_script(101, '''import pathlib,shutil,os
r=pathlib.Path('/opt/aimee-native-compiler');b=r/'release6-backup'
for p in b.iterdir():
 dest=r/p.name;st=dest.stat();shutil.copy2(p,dest);os.chown(dest,st.st_uid,st.st_gid)
''')
        ct_script(100, '''import pathlib,shutil,os
p=pathlib.Path('/etc/aimee-native/preparation.json');b=p.with_name('preparation.before-release6.json')
if b.exists():
 st=p.stat();shutil.copy2(b,p);os.chown(p,st.st_uid,st.st_gid)
''')
        service('start', 'aimee-native-compiler')
        report['rollback'] = 'original_service_and_encoding_revision_restored'
    raise
finally:
    REPORT.write_text(json.dumps(report, indent=2)+'\n')
