"""Three-arm context accounting: native current, ordinary current, full history.
History comparison includes owner compaction as a confound; current-prefix arm
isolates the native attention transport. These are synthetic recall controls,
not proof of semantic tool execution or an effective context multiplier.
"""
import asyncio,json,urllib.request,time,os
from pathlib import Path
from transformers import AutoTokenizer
P=Path(__file__).parent;cfg=json.loads((P/'cpu-config.json').read_text());MODEL=cfg['served_model_name'];PORT=cfg['port'];tok=AutoTokenizer.from_pretrained(cfg['model'],local_files_only=True)
async def ctl(body):
 r,w=await asyncio.open_unix_connection(str(P/'cpu-control.sock'));w.write(json.dumps(body).encode()+b'\n');await w.drain();raw=await r.readline();w.close();await w.wait_closed();return json.loads(raw)
def tokens(messages,generation):return tok.encode(tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=generation,enable_thinking=False),add_special_tokens=False)
def query(body):
 t=time.time();req=urllib.request.Request(f'http://127.0.0.1:{PORT}/v1/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=240) as r:result=json.loads(r.read())
 return result,time.time()-t
async def main():
 history=[];reads=0
 for turn in range(24):
  # Explicitly opaque revisions decrease and include nonnumeric IDs.
  revision=f'r-{100-turn:03d}';value=['coral','teal','amber','violet','silver','cyan'][turn%6]
  pub=f'Owner-resolved current ledger: turn {turn}. Current display colour is {value}. Previous display colours are superseded. Task: state only the current display colour. Recording not performed.'
  withdrawn=await ctl({'op':'withdraw'});generation=withdrawn['generation'];bank=await ctl(dict(op='prepare',generation=generation,publication=pub,revision=revision));assert bank.get('state')=='prepared',bank;active=await ctl(dict(op='refresh',generation=generation));assert active.get('state')=='active',active
  prefix=tokens([dict(role='system',content='Authoritative memory:\n'+pub)],False);cue='What is the current resolved display colour?';suffix=tokens([dict(role='user',content=cue)],True)
  history += [dict(role='user',content='Owner update:\n'+pub),dict(role='user',content=cue)]
  prompts={'native-current':suffix,'ordinary-current':prefix+suffix,'ordinary-history':tokens(history,True)};results={}
  for arm,prompt in prompts.items():
   body=dict(model=MODEL,prompt=prompt,max_tokens=32,temperature=0,return_token_ids=True)
   if arm=='native-current':body['vllm_xargs']=dict(aimee_publication=revision)
   result,seconds=await asyncio.to_thread(query,body);results[arm]=result;answer=result['choices'][0]['text'];metrics=await ctl({'op':'metrics'})
   row=dict(kind='decode',turn=turn,revision=revision,arm=arm,expected=value,answer=answer,correct=value in answer.lower(),finish=result['choices'][0]['finish_reason'],request=body,response=result,seconds=seconds,ordinary_prompt_tokens=len(prompt),private_bank=bank['publication'],metrics=metrics)
   with (P/'cpu-longrun-results.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
  history.append(dict(role='assistant',content=results['ordinary-history']['choices'][0]['text']))
  a,b=results['native-current'],results['ordinary-current'];row=dict(kind='parity',turn=turn,same_tokens=a['choices'][0].get('token_ids')==b['choices'][0].get('token_ids'),same_text=a['choices'][0]['text']==b['choices'][0]['text'])
  with (P/'cpu-longrun-results.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
 with (P/'cpu-longrun-results.jsonl').open('a') as f:f.write(json.dumps(dict(kind='terminal',result=await ctl({'op':'withdraw'})))+'\n')
asyncio.run(main())
