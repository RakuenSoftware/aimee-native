import asyncio,json,urllib.request,time,subprocess,os,hashlib
from pathlib import Path
from transformers import AutoTokenizer
P=Path(__file__).parent;cfg=json.loads((P/'cpu-config.json').read_text());MODEL=cfg['served_model_name'];PORT=cfg['port'];tok=AutoTokenizer.from_pretrained(cfg['model'],local_files_only=True)
CASES=[dict(id='odd',purpose='Propose one odd positive trial workload between10and20 inclusive for project Atlas.',low=10,high=20,parity=1),dict(id='even',purpose='Propose one even positive sample count between21and31 inclusive for project Cedar.',low=21,high=31,parity=0),dict(id='small',purpose='Propose one odd positive batch count between2and8 inclusive for project Drift.',low=2,high=8,parity=1),dict(id='large',purpose='Propose one even positive trial workload between40and50 inclusive for project Ember.',low=40,high=50,parity=0)]
async def ctl(body):
 r,w=await asyncio.open_unix_connection(str(P/'cpu-control.sock'));w.write(json.dumps(body).encode()+b'\n');await w.drain();raw=await r.readline();w.close();await w.wait_closed();return json.loads(raw)
def tokens(messages,generation):return tok.encode(tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=generation,enable_thinking=False),add_special_tokens=False)
def query(body):
 t=time.time();r=urllib.request.Request(f'http://127.0.0.1:{PORT}/v1/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(r,timeout=240) as x:result=json.loads(x.read())
 return result,time.time()-t
def owner(task,view,text):
 r=subprocess.run([str(P/'resolver-v113')],input=json.dumps(dict(id=task['id'],task=task,view=view,text=text))+'\n',capture_output=True,text=True,timeout=30,env=dict(os.environ,AIMEE_RESOLVER_ENDPOINT='',AIMEE_RESOLVER_MODEL=''))
 return json.loads(r.stdout) if r.returncode==0 else dict(error=r.stderr)
def record(row):
 with (P/'cpu-scalar-feedback-v114-results.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
async def main():
 for case in CASES:
  for arm in ['native','ordinary-token-prefix']:
   for replicate in range(2):
    feedback=[];completed=False
    for attempt in range(3):
     pub='Owner task: '+case['purpose']+' Current contribution purpose: propose the candidate value. Contribution format: exactly one integer, with no explanation. All known prerequisites are provided. Aimee owns eligibility checks and recording. No form or external operation has executed.\nAuthoritative checker findings: '+json.dumps(feedback)
     revision=f"feedback-v114-{case['id']}-{arm}-{replicate}-{attempt}";withdrawn=await ctl({'op':'withdraw'});gen=withdrawn['generation'];bank=await ctl(dict(op='prepare',generation=gen,publication=pub,revision=revision));assert bank.get('state')=='prepared',bank;assert (await ctl(dict(op='refresh',generation=gen))).get('state')=='active'
     prefix=tokens([dict(role='system',content='Authoritative memory:\n'+pub)],False);suffix=tokens([dict(role='user',content='Provide your current contribution for the bound task.')],True)
     body=dict(model=MODEL,prompt=suffix if arm=='native' else prefix+suffix,max_tokens=64,temperature=0,return_token_ids=True)
     if arm=='native':body['vllm_xargs']=dict(aimee_publication=revision)
     result,seconds=await asyncio.to_thread(query,body);text=result['choices'][0]['text'];task=dict(id=case['id'],format='scalar_integer',purpose=case['purpose'],capabilities=[dict(id='proposal',kinds=['content'],purpose='Proposed integer value',fields=dict(value=dict(kind='integer',required=True)))])
     target=P/'scalar-feedback-proposals-v114'/f"{case['id']}-{arm}-{replicate}-{attempt}.txt";view=dict(task=task,bindings=[dict(capability_id='proposal',tool='write_file',arguments=dict(path=str(target)),fields=dict(value='content'),field_encoding=dict(value='literal_text'))])
     resolved=await asyncio.to_thread(owner,task,view,text) if result['choices'][0]['finish_reason']=='stop' else dict(error='nonterminal contribution');compiled=resolved.get('compiled');eligible=False;effect=None;finding=None
     if compiled:
      value=int(compiled['arguments']['content']);in_bounds=case['low']<=value<=case['high'];parity_ok=value%2==case['parity'];eligible=in_bounds and parity_ok
      finding=dict(candidate=value,state='accepted' if eligible else 'rejected',in_bounds=in_bounds,parity_correct=parity_ok,reason='valid candidate' if eligible else ('candidate outside declared interval' if not in_bounds else 'candidate has wrong parity for the declared goal'))
      if eligible and compiled['tool']=='write_file' and compiled['arguments']['path']==str(target):
       target.parent.mkdir(exist_ok=True);target.write_text(compiled['arguments']['content']);effect=dict(state='fixture_file_observed',guard='research-fixture-not-enrolled',sha256=hashlib.sha256(target.read_bytes()).hexdigest(),exact_readback=target.read_text()==compiled['arguments']['content']);completed=True
     record(dict(kind='attempt',case=case,arm=arm,replicate=replicate,attempt=attempt,publication=pub,bank=bank,request=body,response=result,seconds=seconds,ordinary_prompt_tokens=len(body['prompt']),private_prefix_tokens=len(prefix),owner_resolution=resolved,eligible=eligible,effect=effect,checker_finding=finding,metrics=await ctl({'op':'metrics'})))
     if completed or finding is None:break
     feedback.append(finding) # Actual checker result, never a repaired replacement.
    record(dict(kind='episode',case=case['id'],arm=arm,replicate=replicate,completed=completed,attempts=attempt+1))
 record(dict(kind='terminal',result=await ctl({'op':'withdraw'})))
asyncio.run(main())
