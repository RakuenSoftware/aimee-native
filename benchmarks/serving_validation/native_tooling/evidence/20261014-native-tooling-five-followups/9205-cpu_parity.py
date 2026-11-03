import json,urllib.request,time
from pathlib import Path
from transformers import AutoTokenizer
P=Path(__file__).parent;tok=AutoTokenizer.from_pretrained('/opt/phase3-research-models/qwen',local_files_only=True)
pub='Task: report the current research display fact. Current resolved display colour is coral. Recording status: not performed. No display device was changed. Aimee-resolved contribution purpose: report the current colour and recording status.'
prefix=tok.encode(tok.apply_chat_template([{'role':'system','content':'Authoritative memory:\n'+pub}],tokenize=False,add_generation_prompt=False,enable_thinking=False),add_special_tokens=False)
for cue in ['What is the current resolved display colour?','Provide your current contribution for the bound task.']:
 suffix=tok.encode(tok.apply_chat_template([{'role':'user','content':cue}],tokenize=False,add_generation_prompt=True,enable_thinking=False),add_special_tokens=False)
 pair={}
 for arm,prompt in [('native',suffix),('ordinary-token-prefix',prefix+suffix)]:
  body=dict(model='research-qwen-native',prompt=prompt,max_tokens=64,temperature=0,return_token_ids=True)
  if arm=='native':body['vllm_xargs']=dict(aimee_publication='999')
  t=time.time();req=urllib.request.Request('http://127.0.0.1:8437/v1/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=180) as r:raw=r.read()
  result=json.loads(raw);pair[arm]=result
  with (P/'cpu-parity-results.jsonl').open('a') as f:f.write(json.dumps(dict(cue=cue,arm=arm,request=body,response=result,seconds=time.time()-t))+'\n')
  print(json.dumps(dict(cue=cue,arm=arm,answer=result['choices'][0]['text'],finish=result['choices'][0]['finish_reason'])),flush=True)
 a,b=pair.values();print(json.dumps(dict(cue=cue,same_text=a['choices'][0]['text']==b['choices'][0]['text'],same_tokens=a['choices'][0].get('token_ids')==b['choices'][0].get('token_ids'))),flush=True)
