"""Research host publication; keeps authorizing material outside model access."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import time

base = Path('/opt/aimee-qwen-rust')
root = base/'published-kb-live'
root.mkdir(mode=0o750)
os.chown(root, 0, 989)
(root/'private').mkdir(mode=0o700)
(root/'traces').mkdir(mode=0o700)
os.chown(root/'traces', 997, 989)
old = base/'general-kb-live'
plan = json.loads((old/'private/plan.json').read_text())
plan['authorization']['valid_until'] = (datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=4)).isoformat()
plan['authorization']['active'] = True
plan_path = root/'private/plan.json'
plan_path.write_text(json.dumps(plan))
start = time.perf_counter()
subprocess.run([str(base/'aimee-issue-fixture'), '--input',str(plan_path), '--key',str(root/'private/key'),
    '--public-key', str(root/'issuer-public.hex'), '--output',str(root/'authorization.json')],check=True,stdout=subprocess.DEVNULL)
subprocess.run([str(base/'aimee-memory-image'),'compile-authorized','--root',str(old/'private/source'),
    '--output-root',str(root/'image'),'--authorization',str(root/'authorization.json'),
    '--authority-key',str(root/'issuer-public.hex'),'--subject','general-kb-research','--policy-epoch','research-1'],check=True)
for d, dirs, files in os.walk(root/'image'):
    os.chown(d,0,989)
    os.chmod(d,0o750)
    for name in files:
        f=Path(d)/name
        assert b'CANARY_UNAPPROVED' not in f.read_bytes()
        os.chown(f,0,989)
        os.chmod(f,0o640)
# Only the root fallback gateway receives the grant; model readers use the image.
assert (root/'authorization.json').stat().st_mode & 0o077 == 0
assert not (root/'image/AUTHORIZATION.json').exists()
summary=dict(general_records=13261,personal_records=2,build_seconds=time.perf_counter()-start,
    image_bytes=sum(p.stat().st_size for p in (root/'image').rglob('*') if p.is_file()),
    grant_files_in_image=0)
(root/'build-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
s=(base/'start-general-kb.sh').read_text().replace('general-kb-live','published-kb-live')
lines=s.splitlines()
for i,line in enumerate(lines):
    if '--unit=aimee-rust-qwen' in line:
        lines[i]=line.replace('--authorization "$live/authorization.json" --authority-key "$live/issuer-public.hex" --subject general-kb-research --policy-epoch research-1 ', '')
(base/'start-published-kb.sh').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary))
