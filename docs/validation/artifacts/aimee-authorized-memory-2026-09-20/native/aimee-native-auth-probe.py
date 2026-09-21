import json,time,urllib.request,urllib.error,subprocess
from pathlib import Path
base=Path('/opt/aimee-auth-native-20260920');root=Path('/opt/aimee-qwen-adapter')
allowed='Give the preferred drink of unit-b03646cbf4, then the home city of unit-121330aded. Separate with a semicolon.'
rows=[]
def ask(case,query=allowed,extra=None):
    body={'messages':[{'role':'system','content':'Answer using the available memory. Return only the requested value or values. If unknown, return unknown.'},{'role':'user','content':query}],'max_tokens':48,'temperature':0}
    if extra:body.update(extra)
    started=time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18792/v1/chat/completions',json.dumps(body).encode(),{'Content-Type':'application/json'}),timeout=120) as r:status=r.status;reply=json.load(r)
    except urllib.error.HTTPError as e:status=e.code;reply=json.loads(e.read())
    row={'case':case,'status':status,'seconds':time.perf_counter()-started,'response':reply};rows.append(row);print(json.dumps(row),flush=True)
    (base/'native-results.json').write_text(json.dumps(rows,indent=2))
# Wait for this runtime's listener, not a stale ready line from an older run.
import socket
for _ in range(180):
    try:
        with socket.create_connection(('127.0.0.1',18792),timeout=1):pass
        break
    except OSError:time.sleep(1)
else:raise RuntimeError('Qwen listener did not become ready')
ask('allowed_cold');ask('allowed_reuse')
ask('unauthorized_record','What is the value associated with unit-edbe6de0e4?')
ask('allowed_after_denial')
ask('model_attempts_scope_expansion',extra={'scope':'all'})
plan_path=base/'private/plan.json';plan=json.loads(plan_path.read_text());plan['authorization']['active']=False
revoked=base/'private/revoked-plan.json';revoked.write_text(json.dumps(plan))
subprocess.run([str(root/'aimee-issue-fixture'),'--input',str(revoked),'--output',str(base/'authorization.json'),'--key',str(base/'private/issuer.key'),'--public-key',str(base/'issuer-public.hex')],check=True,stdout=subprocess.DEVNULL)
ask('revoked_with_cached_states')
checks=[]
for row in rows:
    if row['case'].startswith('allowed'):
        checks.append(row['status']==200 and row['response']['choices'][0]['message']['content'].replace(' ','')=='oolong;Lima')
    else:checks.append(row['status']>=400)
summary={'checks':len(checks),'passed':sum(checks),'all_pass':all(checks)}
(base/'native-summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
if not all(checks):raise SystemExit(1)
