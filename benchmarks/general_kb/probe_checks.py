"""Run focused post-regression diagnostics and bounded native-load tests."""
from pathlib import Path
# Reuse the identical scorer/client without executing the full experiment.
source=Path('/opt/aimee-qwen-rust/probe_followup.py').read_text().split('for _ in range(240):')[0]
exec(compile(source,'probe_followup.py','exec'))
out=root/'post-checks.jsonl'
for case_id in ['planet-3','planet-6','constant-0','personal-1']:
 c=next(c for c in cases if c['id']==case_id)
 for fmt in ['content','json']:
  ask(c,fmt,'post-diagnostic')
history=[]
for i in range(96):
 history.extend([dict(role='user',content=f'Keep task marker {i} available. We will ask a reference question later.'),dict(role='assistant',content='Ready for the reference question.')])
for c in cases[:2]:ask(c,'content','history-96',history)
with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
 futures=[pool.submit(ask,c,'content','concurrency-16') for c in cases[:16]]
 for f in futures:f.result()
