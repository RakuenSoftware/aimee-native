"""Default mode, native-disabled controls, and request validation."""
import argparse,json,urllib.request,urllib.error
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();rows=[]
for case,flags,want,status in [
 ('default',{},'Lima',200),
 ('native-disabled-bank',{'aimee_memory':False,'memory_encoding_granularity':'bank'},'unknown',200),
 ('native-disabled-record',{'aimee_memory':False,'memory_encoding_granularity':'record'},'unknown',200),
 ('invalid-granularity',{'memory_encoding_granularity':'invalid'},None,400),
 ('non-string-granularity',{'memory_encoding_granularity':True},None,400),
]:
 body=dict(messages=[dict(role='system',content='Answer using the available memory. Return only the requested value or values. If unknown, return unknown.'),dict(role='user',content='What is the home city of unit-121330aded? Return only the city.')],temperature=0,max_tokens=12,**flags)
 req=urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',json.dumps(body).encode(),{'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=180) as r:code=r.status;data=json.load(r)
 except urllib.error.HTTPError as e:code=e.code;data=json.load(e)
 assert code==status,(case,code,data)
 if code==200:
  t=json.loads((a.root/'traces'/(data['id']+'.json')).read_text())
  assert data['choices'][0]['message']['content']==want,(case,data)
  if case=='default':assert t['memory_encoding_granularity']=='bank'
  else:assert t['native_reads']==t['memory_encoding_passes']==0 and t['recall_events'] is None
 rows.append(dict(case=case,status=code,response=data))
(a.root/'controls.json').write_text(json.dumps(rows,indent=2)+'\n')
print('5/5 controls passed')
