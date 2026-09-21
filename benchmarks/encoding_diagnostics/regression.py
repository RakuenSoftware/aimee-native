"""Paired wider regression; same publication, prompts, no training or supplied facts."""
import json, math, re, time, unicodedata, urllib.request
from pathlib import Path
b = Path('/opt/aimee-qwen-rust')
root = b / 'keyed-dive-20260920'
SYSTEM = 'Answer using the available memory. Return only the requested value or values. If unknown, return unknown.'
cases = json.loads((b/'general-cases.json').read_text()) + json.loads((b/'new-place-cases.json').read_text())
out = root/'regression.jsonl'
def normalize(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', re.sub(r'\s+', '', s.strip().rstrip('.')).lower()) if not unicodedata.combining(c))
def score(c, s):
    if c['scorer'] == 'number':
        try:
            x = float(s.strip().replace(' ', '').replace(',', '').replace('×10^', 'e').replace('x10^', 'e').replace('−', '-'))
            y = float(c['expected'])
            return math.isfinite(x) and abs(x-y) <= (0 if c['domain']=='iana' else max(abs(y)*1e-5,1e-30))
        except ValueError:
            return False
    return normalize(s) == normalize(c['expected'])
completed = set()
if out.exists():
    completed = {(r['case'],r['format'],r['before_prompt']) for r in map(json.loads,out.read_text().splitlines())}
# Paired native-only controls; diagnostics disabled so measured timings exclude tracing.
for c in cases:
    for fmt, before in [('content',False), ('content',True), ('keyed',True)]:
        if (c['id'],fmt,before) in completed:
            continue
        payload = dict(messages=[dict(role='system',content=SYSTEM),dict(role='user',content=c['query'])],temperature=0,max_tokens=40,aimee_memory=True,preload_memory=True,decode_recall=False,reuse_encoding=False,memory_encoding=fmt,memory_before_prompt=before)
        start = time.perf_counter()
        req = urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=240) as response:
            result=json.load(response)
        trace=json.loads((root/'traces'/(result['id']+'.json')).read_text())
        assert trace['memory_prompt_tokens']==0
        answer=result['choices'][0]['message']['content']
        events=trace.get('recall_events') or []
        refs=[e['bank_memory_ids'] for e in events if 'bank_memory_ids' in e]
        row=dict(case=c['id'],format=fmt,before_prompt=before,answer=answer,expected=c['expected'],pass_=score(c,answer),seconds=time.perf_counter()-start,response=result,prompt_token_ids=trace['prompt_token_ids'],bank_events=refs,memory_prompt_tokens=trace['memory_prompt_tokens'],encoding_passes=trace['memory_encoding_passes'])
        with out.open('a') as f:f.write(json.dumps(row)+'\n')
        print(json.dumps({k:row[k] for k in ['case','format','before_prompt','answer','pass_','seconds']}),flush=True)
