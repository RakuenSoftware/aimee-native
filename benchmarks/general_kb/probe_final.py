"""Actual frozen-Qwen tests: expanded local KB and existing restricted Aimee.
Formats alter only the separate native encoder, never the generation prompt.
"""
import json,time,urllib.request,urllib.error,socket,re,math,concurrent.futures,unicodedata
from pathlib import Path
b=Path('/opt/aimee-qwen-rust');root=b/'kb-followup-20260920';cases=json.loads((b/'general-cases.json').read_text())+json.loads((b/'new-place-cases.json').read_text())
SYSTEM='Answer using the available memory. Return only the requested value or values. If unknown, return unknown.'
out=root/'final-results.jsonl'
def normal(s):return ''.join(c for c in unicodedata.normalize('NFKD',re.sub(r'\s+','',s.strip().rstrip('.')).lower()) if not unicodedata.combining(c))
def score(c,s):
 if c['scorer']=='number':
  s=s.strip().replace(' ','').replace(',','').replace('×10^','e').replace('x10^','e').replace('−','-').replace('**','^')
  try:x=float(s);y=float(c['expected']);return math.isfinite(x) and abs(x-y)<=(0 if c['domain']=='iana' else max(abs(y)*1e-5,1e-30))
  except ValueError:return False
 return normal(s)==normal(c['expected'])
def ask(c,fmt='content',label='baseline',history=None,decode=True):
 messages=[dict(role='system',content=SYSTEM)]+(history or [])+[dict(role='user',content=c['query'])]
 payload=dict(messages=messages,temperature=0,max_tokens=48,aimee_memory=True,memory_encoding=fmt,decode_recall=decode)
 start=time.perf_counter()
 try:
  with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'}),timeout=600) as r:status=r.status;response=json.load(r)
 except urllib.error.HTTPError as e:status=e.code;response=json.loads(e.read())
 answer=response.get('choices',[{'message':{'content':''}}])[0]['message']['content']
 row=dict(case=c['id'],label=label,format=fmt,status=status,answer=answer,expected=c['expected'],pass_=status==200 and score(c,answer),seconds=time.perf_counter()-start,response=response)
 if status==200:
  trace=json.loads((root/'traces'/(response['id']+'.json')).read_text());assert trace['memory_prompt_tokens']==0
  assert trace['generation_prompt'].count(c['query'])>=1
  events=trace.get('recall_events') or []
  row.update(memory_prompt_tokens=0,encoding_passes=trace['memory_encoding_passes'],remote_hits=sum(bool(e.get('aimee_response',{}).get('facts')) and 'restriction' in e.get('aimee_response',{}) for e in events),canonical_refs=[f['memory_ref'] for e in events for f in e.get('aimee_response',{}).get('facts',[])])
  assert all(ref['id']!='999' for ref in row['canonical_refs'])
 with out.open('a') as f:f.write(json.dumps(row)+'\n')
 print(json.dumps({k:row[k] for k in ['case','label','format','status','answer','pass_','seconds']}),flush=True)
 return row
completed=set()
if out.exists():completed={(r['case'],r['label'],r['format']) for r in map(json.loads,out.read_text().splitlines())}
ordered=sorted(cases,key=lambda c:0 if c['id'] in ['constant-0','personal-1'] else 1)
for c in ordered:
 if (c['id'],'final','keyed') not in completed:ask(c,'keyed','final')
# Confirm baseline content behavior on the updated numeric representation.
c=next(c for c in cases if c['id']=='constant-0')
if (c['id'],'decimal-content','content') not in completed:ask(c,'content','decimal-content')
