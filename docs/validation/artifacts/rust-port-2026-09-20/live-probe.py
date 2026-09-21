import json,time,urllib.request,urllib.error,socket,subprocess
from pathlib import Path
root=Path('/opt/aimee-qwen-rust/live')
query='Give the preferred drink of unit-b03646cbf4, then the home city of unit-121330aded. Separate with a semicolon.'
rows=[]
def ask(case,extra=None,prompt=query):
 body={'messages':[{'role':'system','content':'Answer using the available memory. Return only the requested value or values. If unknown, return unknown.'},{'role':'user','content':prompt}],'max_tokens':48,'temperature':0}
 body.update(extra or {})
 t=time.perf_counter()
 try:
  with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',json.dumps(body).encode(),{'Content-Type':'application/json'}),timeout=240) as r: status=r.status;answer=json.load(r)
 except urllib.error.HTTPError as e: status=e.code;answer=json.loads(e.read())
 row=dict(case=case,status=status,seconds=time.perf_counter()-t,response=answer)
 rows.append(row);(root/'results.json').write_text(json.dumps(rows,indent=2));print(json.dumps(row),flush=True)
for _ in range(300):
 try:
  with socket.create_connection(('127.0.0.1',18793),timeout=1):pass
  break
 except OSError:time.sleep(1)
else:raise RuntimeError('server did not start')
ask('none',{'aimee_memory':False})
ask('native_cold')
ask('native_reuse')
ask('attention_only',{'preload_memory':False})
ask('unauthorized_record',prompt='What is the value associated with unit-edbe6de0e4?')
ask('native_after_denial')
ask('scope_expansion',{'scope':'all'})
plan=json.loads((root/'private/plan.json').read_text());plan['authorization']['active']=False
(root/'private/revoked.json').write_text(json.dumps(plan))
subprocess.run(['/opt/aimee-qwen-adapter/aimee-issue-fixture','--input',str(root/'private/revoked.json'),'--output',str(root/'authorization.json'),'--key',str(root/'private/key'),'--public-key',str(root/'issuer-public.hex')],check=True,stdout=subprocess.DEVNULL)
ask('revoked_with_cached_states')
checks={}
for row in rows:
 content=row['response'].get('choices',[{'message':{'content':''}}])[0]['message']['content']
 if row['case']=='none':checks[row['case']]='oolong' not in content and 'Lima' not in content
 elif row['case'].startswith('native') or row['case']=='attention_only':checks[row['case']]=row['status']==200 and content.replace(' ','')=='oolong;Lima'
 else:checks[row['case']]=row['status']>=400
(root/'summary.json').write_text(json.dumps(checks,indent=2));print(checks);assert all(checks.values())
