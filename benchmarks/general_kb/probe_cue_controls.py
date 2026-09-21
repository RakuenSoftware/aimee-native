"""Corrected homonym controls and paired decode-recall check. No supplied facts."""
import json,time,urllib.request
from pathlib import Path
b=Path('/opt/aimee-qwen-rust');root=b/'kb-cue-fix-20260921'
constant=next(c for c in json.loads((b/'general-cases.json').read_text()) if c['id']=='constant-2')
cases=[dict(id='ramona-ambiguous',query='What population does GeoNames report for Ramona US? Return the integer only.',expected='unknown',decode=True),
       dict(id='ramona-qualified',query='What population does GeoNames report for place Ramona US 5385793? Return the integer only.',expected='20292',decode=True),
       dict(id='constant-2-prefill',query=constant['query'],expected=constant['expected'],decode=False),
       dict(id='constant-2-decode',query=constant['query'],expected=constant['expected'],decode=True)]
rows=[]
for c in cases:
    payload=dict(messages=[dict(role='system',content='Answer using the available memory. Return only the requested value or values. If unknown, return unknown.'),dict(role='user',content=c['query'])],temperature=0,max_tokens=40,decode_recall=c['decode'],reuse_encoding=False)
    start=time.perf_counter()
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'}),timeout=300) as r:response=json.load(r)
    t=json.loads((root/'traces'/(response['id']+'.json')).read_text())
    banks=[e['bank_memory_ids'] for e in t['recall_events'] if 'bank_memory_ids' in e]
    answer=response['choices'][0]['message']['content']
    row=dict(case=c['id'],query=c['query'],expected=c['expected'],answer=answer,pass_=answer==c['expected'],response=response,bank=banks[-1] if banks else [],seconds=time.perf_counter()-start)
    if c['id']=='ramona-ambiguous':assert not banks
    if c['id']=='ramona-qualified':assert row['bank'][0]['id']=='geonames.5385793'
    assert t['memory_prompt_tokens']==0
    rows.append(row); print(json.dumps({k:row[k] for k in ['case','answer','pass_']}),flush=True)
(root/'supplemental-controls.json').write_text(json.dumps(rows,indent=2)+'\n')
assert all(r['pass_'] for r in rows)
assert len(rows[2]['bank'])==1 and len(rows[3]['bank'])==2
