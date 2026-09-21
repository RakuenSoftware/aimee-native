"""Check recorded native traces; does not issue memory requests."""
from pathlib import Path
import json,hashlib
root=Path('/opt/aimee-qwen-rust/layered-live-restricted')
results=json.loads((root/'results.json').read_text())
rows=[];none=None
for result in results:
 rid=result['response'].get('id')
 if not rid:continue
 raw=(root/'traces'/f'{rid}.json').read_bytes();t=json.loads(raw)
 assert b'CANARY_UNAPPROVED_' not in raw
 assert t['memory_prompt_tokens']==0
 refs=set();upstream=[]
 for e in t['recall_events'] or []:
  for ref in e.get('bank_memory_ids',[]):
   assert ref['id']!='999';refs.add((ref['namespace'],ref['id']))
  response=e.get('aimee_response',{})
  if 'restriction' in response:
   assert response['restriction']['ids']==[5,6]
   upstream.append([f['id'] for f in response.get('facts',[])])
 if result['case']=='mixed_none':none=t['prompt_token_ids']
 elif result['case'] in ('mixed_native','mixed_reuse','mixed_after_denial'):
  assert t['prompt_token_ids']==none
  assert refs=={('aimee-general-v0','5'),('aimee-published','5'),('aimee-published','6')}
 rows.append(dict(case=result['case'],trace_sha256=hashlib.sha256(raw).hexdigest(),prompt_tokens=len(t['prompt_token_ids']),memory_prompt_tokens=t['memory_prompt_tokens'],main_cache_length=t['main_cache_length'],encoding_passes=t['memory_encoding_passes'],native_reads=t['native_reads'],canonical_refs=sorted(refs),restricted_upstream_reads=upstream))
(root/'trace-audit.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows,indent=2))
