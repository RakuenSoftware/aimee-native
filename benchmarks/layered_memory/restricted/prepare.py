"""Research fixture only: separate public seed, synthetic canary and approved Aimee rows.
Never use this signing path as a production authorization issuer.
"""
import json,datetime,subprocess,os,hashlib
from pathlib import Path
base=Path('/opt/aimee-qwen-rust');root=base/'layered-live-restricted'
root.mkdir(mode=0o750);os.chown(root,0,989)
private=root/'private';private.mkdir(mode=0o700)
traces=root/'traces';traces.mkdir(mode=0o700);os.chown(traces,997,989)
reader=base/'aimee-memory-image';source=private/'source'
def cli(*args):
 raw=subprocess.check_output([str(reader),*map(str,args)],text=True)
 return json.loads(raw) if raw else None
def build(name,change):
 p=private/(name+'.json');p.write_text(json.dumps(change))
 return cli('build','--root',source,'--input',p)['view']
seed=json.loads((base/'knowledge/general-v0/records.json').read_text())
# Canary not part of the published starter KB. Deliberately collides with Aimee ID 5.
canary=dict(namespace=seed['namespace'],id='5',revision='research-canary-v1',scope={'type':'global','value':'_global'},key='research.native-general.finish',content='The default finish of unit-b03646cbf4 is teal.',kind='fact',tier='L3',confidence=1,lifecycle='active')
seed['records'].append(canary)
general=build('general-with-canary',seed)
old=json.loads(Path('/opt/aimee-auth-native-20260920/private/plan.json').read_text())
records=old['records']
until=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=2)).isoformat()
queries=json.loads((base/'knowledge/general-v0/queries.json').read_text())
contracts=[]
def response(rs):
 return {'status':'ok','facts':[r.get('metadata',{}).get('aimee_response_fact') or {k:r[k] for k in ['id','scope','tier','kind','key','content','confidence']} for r in rs],'windows':[],'active_context_missing':False}
def contract(q,rs):
 contracts.append(dict(query=q,limit=2,authority='research-aimee-103',grants=['user:_user'],valid_until=until,dependencies=[{k:r[k] for k in ['namespace','id','revision']} for r in rs],response=response(rs)))
for q in queries:
 contract(q['query'],[next(r for r in seed['records'] if r['id']==q['memory_id'])])
mixed='Give the default finish of unit-b03646cbf4, then the preferred drink of unit-b03646cbf4, then the home city of unit-121330aded. Separate with semicolons.'
contract(mixed,[canary,records[0]])
units='Give the multiplier for the binary prefix kibi, then the preferred drink of unit-b03646cbf4, then the home city of unit-121330aded. Separate with semicolons.'
contract(units,[next(r for r in seed['records'] if r['id']=='binary.prefix.kibi'),records[0]])
# Deliberately unapproved third local row tests physical exclusion.
withheld=dict(records[0],id='999',content='CANARY_UNAPPROVED_PERSONAL')
head=build('server',dict(namespace='aimee-published',kind='server',generation=1,upstream=general,records=records+[withheld],source='approved research Aimee records plus withheld test control',coverage=['facts'],read_contracts=contracts))
cli('publish','--root',source,'--view',head)
plan=dict(authorization=dict(version=1,id='layered-rust-research',subject='research-layered-port',policy_epoch='research-1',source_view=head,active=True,valid_until=until,grants=['user:_user']),records=seed['records']+records,reads=contracts)
(private/'plan.json').write_text(json.dumps(plan))
subprocess.run(['/opt/aimee-qwen-adapter/aimee-issue-fixture','--input',str(private/'plan.json'),'--key',str(private/'key'),'--public-key',str(root/'issuer-public.hex'),'--output',str(root/'authorization.json')],check=True)
cli('compile-authorized','--root',source,'--output-root',root/'image','--authorization',root/'authorization.json','--authority-key',root/'issuer-public.hex','--subject','research-layered-port','--policy-epoch','research-1')
for p in [root/'authorization.json',root/'issuer-public.hex']:os.chown(p,0,989);os.chmod(p,0o640)
for d,dirs,files in os.walk(root/'image'):
 os.chown(d,0,989);os.chmod(d,0o750)
 for name in files:
  p=Path(d)/name;assert b'CANARY_UNAPPROVED_PERSONAL' not in p.read_bytes()
  os.chown(p,0,989);os.chmod(p,0o640)
(root/'queries.json').write_text(json.dumps({'mixed':mixed,'units':units,'seed':queries}))
(root/'build-summary.json').write_text(json.dumps(dict(source_view=head,seed_records=25,synthetic_general_canaries=1,approved_personal_records=2,excluded_personal_records=1,published_read_contracts=len(contracts),authorized_image_bytes=sum(p.stat().st_size for p in (root/'image').rglob('*') if p.is_file())),indent=2))
print((root/'build-summary.json').read_text())
