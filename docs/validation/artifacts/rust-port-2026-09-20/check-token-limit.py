import json,urllib.request
from pathlib import Path
body={'messages':[{'role':'user','content':'Reply with exactly hello.'}],'max_tokens':1,'aimee_memory':False,'temperature':0}
with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',json.dumps(body).encode(),{'Content-Type':'application/json'}),timeout=60) as r: out=json.load(r)
assert out['choices'][0]['finish_reason']=='length'
assert out['usage']['completion_tokens']==1
Path('/opt/aimee-qwen-rust/live/evidence/token-limit.json').write_text(json.dumps(out,indent=2))
print('token-limit check passed')
