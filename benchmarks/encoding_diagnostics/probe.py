"""Controlled probes through the actual native adapter/Aimee path, no supplied facts.
The generation prompt and greedy settings are identical across native variants.
"""
import argparse,json,math,socket,time,urllib.request,urllib.error
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--phase',choices=['formats','positions','controls'],required=True);a=p.parse_args()
b=Path('/opt/aimee-qwen-rust');root=b/'keyed-dive-20260920';out=root/(a.phase+'.jsonl')
cases=[c for c in json.loads((b/'general-cases.json').read_text()) if c['id'] in ['planet-3','planet-6','personal-0','personal-1']]
SYSTEM='Answer using the available memory. Return only the requested value or values. If unknown, return unknown.'
def score(c,s):
 if c['scorer']=='number':
  try:return abs(float(s.replace(' ',''))-float(c['expected']))<=abs(float(c['expected']))*1e-5
  except ValueError:return False
 return s.strip().lower()==c['expected'].lower()
def ask(c,fmt,shift=0,before=False,system=SYSTEM,native=True,tag=''):
 payload=dict(messages=[dict(role='system',content=system),dict(role='user',content=c['query'])],temperature=0,max_tokens=40,aimee_memory=native,preload_memory=True,decode_recall=False,reuse_encoding=False,memory_encoding=fmt,memory_diagnostics=8,memory_position_shift=shift,memory_before_prompt=before,diagnostic_candidates=['unknown','2','5','oolong','Lima','611','358'])
 start=time.perf_counter()
 try:
  with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'}),timeout=240) as r:status=r.status;response=json.load(r)
 except urllib.error.HTTPError as e:status=e.code;response=json.loads(e.read())
 answer=response.get('choices',[{'message':{'content':''}}])[0]['message']['content']
 row=dict(case=c['id'],format=fmt,shift=shift,before_prompt=before,native=native,tag=tag,status=status,answer=answer,expected=c['expected'],pass_=status==200 and score(c,answer),seconds=time.perf_counter()-start,response=response)
 if status==200:
  trace=json.loads((root/'traces'/(response['id']+'.json')).read_text());events=trace.get('recall_events') or []
  row.update(prompt_token_ids=trace['prompt_token_ids'],encodings=trace['memory_encoding_passes'],encoding_events=[{k:e[k] for k in ['step','status','bank_memory_ids','encoding'] if k in e} for e in events if 'encoding' in e])
  if native:
   assert trace['memory_prompt_tokens']==0
   assert row['encoding_events'],row
 with out.open('a') as f:f.write(json.dumps(row)+'\n')
 print(json.dumps({k:row[k] for k in ['case','format','shift','before_prompt','native','tag','answer','pass_','seconds']}),flush=True)
 return row
for _ in range(360):
 try:
  with socket.create_connection(('127.0.0.1',18793),timeout=1):pass
  break
 except OSError:time.sleep(1)
else:raise RuntimeError('model unavailable')
completed=set()
if out.exists():
 for row in map(json.loads,out.read_text().splitlines()):completed.add((row['case'],row['format'],row['shift'],row['before_prompt'],row['native'],row['tag']))
def run(c,fmt,shift=0,before=False,system=SYSTEM,native=True,tag=''):
 if (c['id'],fmt,shift,before,native,tag) not in completed:return ask(c,fmt,shift,before,system,native,tag)
if a.phase=='formats':
 for fmt in ['content','keyed','keyed-neutral','keyed-suffix','json']:
  for c in cases:run(c,fmt)
elif a.phase=='positions':
 for fmt in ['content','keyed']:
  for c in cases:run(c,fmt,before=True,tag='past-addresses')
 for shift in [-16,-8,-4,4,8,16]:
  for c in cases:run(c,'keyed',shift=shift,tag='shift-sweep')
else:
 rows=[json.loads(x) for x in (root/'formats.jsonl').read_text().splitlines()]
 for fmt in ['content','keyed']:
  for c in cases:
   row=next(r for r in rows if r['case']==c['id'] and r['format']==fmt)
   # Same Aimee-returned factual bytes, explicit text control only.
   encoding=row['encoding_events'][-1]['encoding']['text']
   run(c,fmt,system=SYSTEM+'\n'+encoding,native=False,tag='text-control')
