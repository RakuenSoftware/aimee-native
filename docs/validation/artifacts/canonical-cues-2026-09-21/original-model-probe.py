"""Unchanged 46-question regression on the new image, with canonical/alias controls."""
import json,math,re,time,unicodedata,urllib.request
from pathlib import Path
b=Path('/opt/aimee-qwen-rust');root=b/'kb-cue-fix-20260921'
cases=json.loads((b/'general-cases.json').read_text())+json.loads((b/'new-place-cases.json').read_text())
controls=[dict(id='alias-owner-ramona',domain='geonames',query='What population does GeoNames report for Ramona US? Return the integer only.',expected='20292',scorer='number'),
          dict(id='alias-owner-port',domain='geonames',query='What population does GeoNames report for Port-de-Lanne FR? Return the integer only.',expected='759',scorer='number'),
          dict(id='true-ambiguity',domain='geonames',query='What population does GeoNames report for Springfield US? Return the integer only.',expected='unknown',scorer='text')]
def score(c,s):
    if c['scorer']=='number':
        try:
            x=float(s.strip().replace(' ',''));y=float(c['expected'])
            return math.isfinite(x) and abs(x-y)<=(0 if c['domain'] in ['iana','geonames'] else max(abs(y)*1e-5,1e-30))
        except ValueError:return False
    def norm(s):return ''.join(x for x in unicodedata.normalize('NFKD',re.sub(r'\s+','',s.strip().rstrip('.')).lower()) if not unicodedata.combining(x))
    return norm(s)==norm(c['expected'])
out=root/'model-results.jsonl';done=set()
if out.exists():done={(r['case'],r['format']) for r in map(json.loads,out.read_text().splitlines())}
work=[(c,'content') for c in cases+controls]+[(c,'keyed') for c in cases if c['id'] in ['new-place-2','new-place-4','planet-3','planet-6','personal-0','personal-1']]
for c,fmt in work:
    if (c['id'],fmt) in done:continue
    payload=dict(messages=[dict(role='system',content='Answer using the available memory. Return only the requested value or values. If unknown, return unknown.'),dict(role='user',content=c['query'])],temperature=0,max_tokens=40,memory_encoding=fmt)
    start=time.perf_counter()
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'}),timeout=300) as r:response=json.load(r)
    trace=json.loads((root/'traces'/(response['id']+'.json')).read_text());answer=response['choices'][0]['message']['content']
    assert trace['memory_prompt_tokens']==0 and trace['memory_before_prompt'] is True
    refs=[e['bank_memory_ids'] for e in trace['recall_events'] if 'bank_memory_ids' in e]
    if c['id']=='true-ambiguity':assert not refs,refs
    row=dict(case=c['id'],format=fmt,query=c['query'],answer=answer,expected=c['expected'],pass_=score(c,answer),seconds=time.perf_counter()-start,response=response,prompt_token_ids=trace['prompt_token_ids'],bank=refs[-1] if refs else [],memory_prompt_tokens=0)
    with out.open('a') as f:f.write(json.dumps(row)+'\n')
    print(json.dumps({k:row[k] for k in ['case','format','answer','pass_','seconds']}),flush=True)
rows=list(map(json.loads,out.read_text().splitlines()));assert len(rows)==55
(root/'model-summary.json').write_text(json.dumps({mode:dict(total=sum(r['format']==mode for r in rows),passed=sum(r['format']==mode and r['pass_'] for r in rows)) for mode in ['content','keyed']},indent=2)+'\n')
assert all(r['pass_'] for r in rows),[(r['case'],r['answer']) for r in rows if not r['pass_']]
