"""Live evaluation client only; the model, reader and gateway contain no Python."""
import json,time,urllib.request,urllib.error,socket,subprocess,os
from pathlib import Path
base=Path('/opt/aimee-qwen-rust');root=base/'layered-live-v2';q=json.loads((root/'queries.json').read_text())
lib='/opt/aimee-native-p0-training/lib/python3.13/site-packages/torch/lib'
# Verify every starter query through the actual Rust client and signed reader.
args=[str(base/'target/release/aimee-qwen'),'read-check','--image-reader',str(base/'aimee-memory-image'),'--memory-image',str(root/'image'),'--authorization',str(root/'authorization.json'),'--authority-key',str(root/'issuer-public.hex'),'--subject','research-layered-port','--policy-epoch','research-1','--read-gateway','/run/aimee-rust-native/search.sock','--read-authority','research-aimee-103']
inputs=[{'op':'begin'}]+[{'op':'native_search','query':x['query'],'limit':2} for x in q['seed']]
p=subprocess.run(args,input=''.join(json.dumps(x)+'\n' for x in inputs),text=True,capture_output=True,env=dict(os.environ,LD_LIBRARY_PATH=lib),check=True)
reads=[json.loads(line)['result'] for line in p.stdout.splitlines()]
assert len(reads)==26
for item,reply in zip(q['seed'],reads[1:]):
 assert len(reply['facts'])==1 and reply['facts'][0]['memory_ref']['namespace']=='aimee-general-v0' and reply['facts'][0]['memory_ref']['id']==item['memory_id']
(root/'seed-read-results.json').write_text(json.dumps(reads,indent=2))
for _ in range(300):
 try:
  with socket.create_connection(('127.0.0.1',18793),timeout=1):pass
  break
 except OSError:time.sleep(1)
else:raise RuntimeError('model unavailable')
rows=[]
def ask(case,query,extra=None):
 payload={'messages':[{'role':'system','content':'Answer using the available memory. Return only the requested value or values. If unknown, return unknown.'},{'role':'user','content':query}],'temperature':0,'max_tokens':32}
 payload.update(extra or {});start=time.perf_counter()
 try:
  with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'}),timeout=180) as r:status=r.status;response=json.load(r)
 except urllib.error.HTTPError as e:status=e.code;response=json.loads(e.read())
 row=dict(case=case,status=status,seconds=time.perf_counter()-start,response=response);rows.append(row);(root/'results.json').write_text(json.dumps(rows,indent=2));print(json.dumps(row),flush=True)
ask('mixed_none',q['mixed'],{'aimee_memory':False})
ask('mixed_native',q['mixed'])
ask('mixed_reuse',q['mixed'])
ask('real_units_and_personal',q['units'])
ask('personal_attention_only','Give the preferred drink of unit-b03646cbf4, then the home city of unit-121330aded. Separate with a semicolon.',{'preload_memory':False})
ask('foreign_record','What is the value associated with unit-edbe6de0e4?')
ask('mixed_after_denial',q['mixed'])
plan=json.loads((root/'private/plan.json').read_text());plan['authorization']['active']=False
(root/'private/revoked.json').write_text(json.dumps(plan))
subprocess.run(['/opt/aimee-qwen-adapter/aimee-issue-fixture','--input',str(root/'private/revoked.json'),'--key',str(root/'private/key'),'--public-key',str(root/'issuer-public.hex'),'--output',str(root/'authorization.json')],check=True,stdout=subprocess.DEVNULL)
ask('revoked_mixed',q['mixed'])
checks={}
for r in rows:
 value=r['response'].get('choices',[{'message':{'content':''}}])[0]['message']['content'].replace(' ','').lower()
 if r['case']=='mixed_none':ok='teal' not in value and 'oolong' not in value
 elif r['case'] in ['mixed_native','mixed_reuse','mixed_after_denial']:ok=r['status']==200 and value=='teal;oolong;lima'
 elif r['case']=='real_units_and_personal':ok=r['status']==200 and value in ['1024;oolong;lima','2^10;oolong;lima','1,024;oolong;lima']
 elif r['case']=='personal_attention_only':ok=r['status']==200 and value=='oolong;lima'
 else:ok=r['status']>=400
 checks[r['case']]=ok
checks['starter_local_reads']=len(reads)-1==25
(root/'summary.json').write_text(json.dumps(checks,indent=2));print(checks);assert all(checks.values())
