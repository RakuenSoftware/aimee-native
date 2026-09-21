"""Isolated source-format update through the real publisher; fixture approval."""
import json,subprocess,time
from pathlib import Path
b=Path('/opt/aimee-qwen-rust');r=b/'kb-followup-20260920';p=r/'private/local';source=b/'kb-scale-20260920/249105/private/source'
plan=json.loads((p/'plan.json').read_text());changed=json.loads((b/'decimal-rows.json').read_text());by={x['id']:x for x in changed}
head=plan['authorization']['source_view']
delta=dict(namespace='aimee-general-v1',kind='general',generation=2,previous=head,source='Exact finite-decimal rendering of pinned NIST quantities',coverage=['canonical_facts','source_provenance'],records=changed)
path=p/'numeric-delta.json';path.write_text(json.dumps(delta,separators=(',',':')))
def cli(*args):
 raw=subprocess.check_output([str(b/'aimee-memory-image-next'),*map(str,args)],text=True)
 return json.loads(raw) if raw.strip() else None
new=cli('build','--root',source,'--input',path)['view']
if json.loads((source/'CURRENT').read_text())['view']!=new:cli('publish','--root',source,'--view',new,'--expected',head)
plan['authorization']['source_view']=new;plan['authorization']['id']='expanded-kb-decimal-rendering'
plan['records']=[by.get(x['id'],x) for x in plan['records']]
for c in plan['authorization']['reference_cues']:
 if c['ref']['id'] in by:c['ref']['revision']=by[c['ref']['id']]['revision']
(p/'numeric-plan.json').write_text(json.dumps(plan,ensure_ascii=False,separators=(',',':')))
subprocess.run([str(b/'aimee-issue-fixture'),'--input',str(p/'numeric-plan.json'),'--key',str(p/'key'),'--public-key',str(p/'public'),'--output',str(p/'grant.next')],check=True,stdout=subprocess.DEVNULL)
(p/'grant.next').replace(p/'grant')
start=time.perf_counter();out=cli('sync-published','--root',source,'--output-root',r/'image','--authorization',p/'grant','--authority-key',p/'public','--subject','scale','--policy-epoch','test','--reader-gid','989')
summary=dict(changed_records=len(changed),seconds=time.perf_counter()-start,result=out)
(r/'numeric-update.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
