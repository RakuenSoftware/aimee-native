"""Research publication on the model host. General KB never goes into server DB."""
from pathlib import Path
import datetime,json,os,subprocess,time
base=Path('/opt/aimee-qwen-rust');root=base/'general-kb-live';root.mkdir(mode=0o750);os.chown(root,0,989)
private=root/'private';private.mkdir(mode=0o700);traces=root/'traces';traces.mkdir(mode=0o700);os.chown(traces,997,989)
reader=base/'aimee-memory-image';source=private/'source'
def cli(*args):
 raw=subprocess.check_output([str(reader),*map(str,args)],text=True);return json.loads(raw) if raw else None
def build(name,change):
 p=private/(name+'.json');p.write_text(json.dumps(change));return cli('build','--root',source,'--input',p)['view']
start=time.perf_counter();seed=json.loads((base/'records.json').read_text());general=build('general',seed)
records=json.loads(Path('/opt/aimee-auth-native-20260920/private/plan.json').read_text())['records']
withheld=dict(records[0],id='999',content='CANARY_UNAPPROVED_PERSONAL')
head=build('server',dict(namespace='aimee-published',kind='server',generation=1,upstream=general,records=records+[withheld],source='approved synthetic personal facts plus excluded control',coverage=['facts']))
cli('publish','--root',source,'--view',head)
a=dict(version=1,id='general-kb-research-v1',subject='general-kb-research',policy_epoch='research-1',source_view=head,active=True,valid_until=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=8)).isoformat(),grants=['user:_user'],reference_lookups=[dict(namespace=seed['namespace'],authority='research-aimee-103',mode='exact-key-v1')])
plan=dict(authorization=a,records=seed['records']+records,reads=[]);(private/'plan.json').write_text(json.dumps(plan))
subprocess.run([str(base/'aimee-issue-fixture'),'--input',str(private/'plan.json'),'--key',str(private/'key'),'--public-key',str(root/'issuer-public.hex'),'--output',str(root/'authorization.json')],check=True)
cli('compile-authorized','--root',source,'--output-root',root/'image','--authorization',root/'authorization.json','--authority-key',root/'issuer-public.hex','--subject','general-kb-research','--policy-epoch','research-1')
for p in [root/'authorization.json',root/'issuer-public.hex']:os.chown(p,0,989);os.chmod(p,0o640)
for d,dirs,files in os.walk(root/'image'):
 os.chown(d,0,989);os.chmod(d,0o750)
 for name in files:
  p=Path(d)/name;assert b'CANARY_UNAPPROVED_PERSONAL' not in p.read_bytes();os.chown(p,0,989);os.chmod(p,0o640)
(root/'build-summary.json').write_text(json.dumps(dict(source_view=head,general_records=len(seed['records']),personal_records=len(records),authorized_image_bytes=sum(p.stat().st_size for p in (root/'image').rglob('*') if p.is_file()),build_seconds=time.perf_counter()-start,read_contracts=0),indent=2))
print((root/'build-summary.json').read_text())
# Adapt only deployment paths/subject; Qwen weights and Rust binary unchanged.
s=(base/'start-restricted.sh').read_text().replace('layered-live-restricted','general-kb-live').replace('research-layered-port','general-kb-research').replace('--memory-limit 2','--memory-limit 4').replace('--property=RuntimeMaxSec=1h','--property=RuntimeMaxSec=3h')
(base/'start-general-kb.sh').write_text(s)
