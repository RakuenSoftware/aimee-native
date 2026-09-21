"""Evaluation client. General reads execute locally in the Go image reader.
The text arm is a diagnostic oracle for consumption, not a whole-KB alternative.
"""
from pathlib import Path
import json,time,urllib.request,urllib.error,socket,re,math,sys,os
base=Path('/opt/aimee-qwen-rust');root=base/'general-kb-live'
cases=json.loads((base/'general-cases.json').read_text());records={r['id']:r for r in json.loads((base/'records.json').read_text())['records']}
personal=json.loads((root/'private/plan.json').read_text())['records'][-2:]
out=root/os.environ.get('RESULT_FILE','results.jsonl')
SYSTEM='Answer using the available memory. Return only the requested value or values. If unknown, return unknown.'
def normal(s):return re.sub(r'\s+','',s.strip().rstrip('.')).lower()
def score(c,answer):
 if c['scorer']=='number':
  s=answer.strip().replace(' ','').replace(',','').replace('×10^','e').replace('x10^','e').replace('−','-').replace('**','^')
  try:x=float(s);y=float(c['expected']);return math.isfinite(x) and abs(x-y)<= (0 if c['domain']=='iana' else max(abs(y)*1e-5,1e-30))
  except ValueError:return False
 return normal(answer)==normal(c['expected'])
for _ in range(360):
 try:
  with socket.create_connection(('127.0.0.1',18793),timeout=1):pass
  break
 except OSError:time.sleep(1)
else:raise RuntimeError('model unavailable')
completed=set()
if out.exists():completed={(r['case'],r['mode']) for r in map(json.loads,out.read_text().splitlines())}
for c in cases:
 for mode in os.environ.get('MODES','none,native,text').split(','):
  if (c['id'],mode) in completed:continue
  system=SYSTEM
  if mode=='text':
   facts=[records[k]['content'] for k in c['memory_ids']]
   if c.get('personal'):facts += [r['content'] for r in personal]
   if facts:system+='\nAuthoritative reference facts:\n'+'\n'.join(facts)
  payload=dict(messages=[dict(role='system',content=system),dict(role='user',content=c['query'])],temperature=0,max_tokens=48,aimee_memory=mode=='native')
  t=time.perf_counter()
  try:
   with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'}),timeout=240) as r:status=r.status;response=json.load(r)
  except urllib.error.HTTPError as e:status=e.code;response=json.loads(e.read())
  answer=response.get('choices',[{'message':{'content':''}}])[0]['message']['content']
  row=dict(case=c['id'],domain=c['domain'],mode=mode,status=status,answer=answer,expected=c['expected'],pass_=status==200 and score(c,answer),seconds=time.perf_counter()-t,response=response)
  if mode=='native' and status==200:
   trace=json.loads((root/'traces'/(response['id']+'.json')).read_text())
   assert trace['memory_prompt_tokens']==0
   events=trace['recall_events'] or [];refs=[];remote=0;local=0
   for e in events:
    reply=e.get('aimee_response',{})
    for f in reply.get('facts',[]):
     ref=f.get('memory_ref',{});refs.append(ref)
     assert ref.get('id')!='999'
     if ref.get('namespace')=='aimee-general-v1':assert 'restriction' not in reply
    if 'restriction' in reply:remote+=1
    elif reply.get('facts'):local+=1
   row.update(memory_prompt_tokens=0,canonical_refs=refs,local_events=local,remote_events=remote,encoding_passes=trace['memory_encoding_passes'])
  with out.open('a') as f:f.write(json.dumps(row)+'\n')
  print(json.dumps({k:row[k] for k in ['case','mode','status','answer','expected','pass_','seconds']}),flush=True)
