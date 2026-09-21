"""Paired record/bank encoding experiment against the same live Aimee source.
No memory payloads are supplied by this driver. Keep failed results unchanged.
"""
import argparse,json,math,re,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--cases',type=Path,required=True);a=p.parse_args()
cases=json.loads(a.cases.read_text())
selected=[c for c in cases if c['id'] in ['planet-3','planet-6','constant-2','personal-0','personal-1']]
selected += [dict(id='drink',query='What is the preferred drink of unit-b03646cbf4? Return only the drink.',expected='oolong',scorer='text'),dict(id='city',query='What is the home city of unit-121330aded? Return only the city.',expected='Lima',scorer='text')]
# Singletons first, then composition: warm record cache must be reusable across
# different working sets, rather than only repeated identical questions.
selected=selected[-2:]+selected[:-2]
out=a.root/'results.jsonl'
assert not out.exists(),'Use a new output directory; never overwrite evidence'
rows=[]
for mode in ['bank','record']:
 for reuse in [False,True,True]:
  for c in selected:
   body=dict(messages=[dict(role='system',content='Answer using the available memory. Return only the requested value or values. If unknown, return unknown.'),dict(role='user',content=c['query'])],temperature=0,max_tokens=40,decode_recall=True,reuse_encoding=reuse,memory_encoding_granularity=mode)
   start=time.perf_counter()
   with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=300) as r: response=json.load(r)
   trace=json.loads((a.root/'traces'/(response['id']+'.json')).read_text())
   answer=response['choices'][0]['message']['content'];expected=c['expected']
   try:ok=math.isclose(float(answer),float(expected),rel_tol=1e-5) if c['scorer']=='number' else re.sub(r'\s+','',answer).lower()==re.sub(r'\s+','',expected).lower()
   except ValueError:ok=False
   events=trace['recall_events'];banks=[e['bank_memory_ids'] for e in events if 'bank_memory_ids' in e]
   assert trace['memory_prompt_tokens']==0
   row=dict(case=c['id'],mode=mode,reuse=reuse,query=c['query'],expected=expected,answer=answer,pass_=ok,seconds=time.perf_counter()-start,id=response['id'],encodings=trace['memory_encoding_passes'],encoding_ms=sum(e.get('encoding_elapsed_ms',0) for e in events),encoded_tokens=sum(e.get('tokens_encoded',0) for e in events),record_working_set_hits=sum(e.get('record_working_set_hits',0) for e in events),record_cache_hits=sum(e.get('record_cache_hits',0) for e in events),bank=banks[-1] if banks else [],prompt_token_ids=trace['prompt_token_ids'])
   rows.append(row)
   with out.open('a') as f:f.write(json.dumps(row)+'\n')
   print(json.dumps({k:row[k] for k in ['case','mode','reuse','answer','pass_','encodings','encoding_ms','record_cache_hits']}),flush=True)
summary={mode:dict(total=sum(r['mode']==mode for r in rows),passed=sum(r['mode']==mode and r['pass_'] for r in rows)) for mode in ['bank','record']}
(a.root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary),flush=True)
