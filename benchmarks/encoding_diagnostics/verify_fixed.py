"""Live regression of normal requests (no positional override or diagnostic mode).
Run against the fixed Rust server and the approved synthetic Aimee publication.
"""
import json, time, urllib.error, urllib.request
from pathlib import Path
b=Path('/opt/aimee-qwen-rust'); root=b/'keyed-dive-20260920/fixed'
cases=[c for c in json.loads((b/'general-cases.json').read_text()) if c['id'] in ['planet-3','planet-6','personal-0','personal-1']]
out=root/'results.jsonl'
failures=[]
def score(c,s):
    if c['scorer']=='number':
        try:return abs(float(s)-float(c['expected'])) <= abs(float(c['expected']))*1e-5
        except ValueError:return False
    return [p.strip().lower() for p in s.split(';')]==[p.strip().lower() for p in c['expected'].split(';')]
def ask(c,fmt,tag,history=None,native=True):
    messages=[dict(role='system',content='Answer using the available memory. Return only the requested value or values. If unknown, return unknown.')]+(history or [])+[dict(role='user',content=c['query'])]
    payload=dict(messages=messages,temperature=0,max_tokens=40,memory_encoding=fmt,aimee_memory=native)
    start=time.perf_counter()
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'}),timeout=300) as response:r=json.load(response)
    t=json.loads((root/'traces'/(r['id']+'.json')).read_text())
    assert t['memory_prompt_tokens']==0
    assert not t['logit_trace'] and not t['attention_trace']
    if native:
        assert t['memory_before_prompt'] is True
        assert t['memory_position_offset'] < 0
    else:
        assert t['memory_encoding_passes']==0 and t['native_reads']==0
    answer=r['choices'][0]['message']['content']
    row=dict(case=c['id'],format=fmt,tag=tag,native=native,answer=answer,expected=c['expected'],pass_=score(c,answer),seconds=time.perf_counter()-start,response=r,encodings=t['memory_encoding_passes'],reads=t['native_reads'],offset=t['memory_position_offset'],prompt_token_ids=t['prompt_token_ids'],bank_events=[e['bank_memory_ids'] for e in t.get('recall_events') or [] if 'bank_memory_ids' in e],statuses=[e['status'] for e in t.get('recall_events') or []])
    with out.open('a') as f:f.write(json.dumps(row)+'\n')
    print(json.dumps({k:row[k] for k in ['case','format','tag','answer','pass_','encodings','offset']}),flush=True)
    if native and not row['pass_']: failures.append((c['id'],fmt,tag,answer))
    return row
for tag in ['normal','repeat-cached']:
    for fmt in ['content','keyed']:
        for c in cases:
            r=ask(c,fmt,tag)
            if tag=='repeat-cached':assert r['encodings']==0, 'repeat unexpectedly re-encoded'
for c in cases:ask(c,'content','no-memory',native=False)
history=[]
for i in range(32):
    history.extend([dict(role='user',content=f'Keep task marker {i} available. We will ask a reference question later.'),dict(role='assistant',content='Ready for the reference question.')])
for fmt in ['content','keyed']:
    ask(next(c for c in cases if c['id']=='personal-1'),fmt,'history-32',history=history)
# Normal serving must not allow a caller to restore overlapping coordinates.
payload=dict(messages=[dict(role='user',content='Hello')],memory_before_prompt=False,max_tokens=1)
try:
    urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'}),timeout=30)
    raise AssertionError('diagnostic override accepted on normal server')
except urllib.error.HTTPError as e:
    assert e.code==400
    (root/'diagnostics-rejection.json').write_text(json.dumps(dict(status=e.code,response=json.loads(e.read())))+'\n')

assert not failures, f'native answer regressions: {failures}'
