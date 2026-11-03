"""Frozen synthetic additional-need episodes; no oracle enters inference."""
import asyncio,json,urllib.request,time,subprocess,os,hashlib
from pathlib import Path
from transformers import AutoTokenizer
P=Path(__file__).parent
CONFIG=json.loads((P/'cpu-config.json').read_text());MODEL=CONFIG.get('served_model_name','research-qwen-native');PORT=CONFIG.get('port',8437)
# Adapt to exact launch config names, never guess tokenizer checkpoint.
MODEL=os.environ.get('EPISODE_MODEL',MODEL);PORT=int(os.environ.get('EPISODE_PORT',PORT));CHECKPOINT=os.environ.get('EPISODE_CHECKPOINT','/opt/phase3-research-models/qwen')
tok=AutoTokenizer.from_pretrained(CHECKPOINT,local_files_only=True)
CASES=[
 dict(id='packing',task='Assess whether the synthetic packing line can meet demand.',facts='Demand:100 units/hour. Nominal capacity:120 units/hour. All standard prerequisites have been provided. The latest motor temperature is unusually high at94C.',sources={'temperature-adjusted capacity':'80 units/hour','maintenance interval':'30 days'},needed='temperature-adjusted capacity'),
 dict(id='network',task='Assess whether the synthetic link can sustain the requested transfer.',facts='Requested throughput:70MB/s. Nominal throughput:90MB/s. All standard prerequisites have been provided. Recent logs show retransmission spikes.',sources={'measured useful throughput':'52MB/s','link installation date':'2024'},needed='measured useful throughput'),
 dict(id='storage',task='Assess whether the synthetic scratch pool can hold the pending batch.',facts='Pending batch:40GB. Reported free capacity:60GB. All standard prerequisites have been provided. Snapshot accounting has recently been inconsistent.',sources={'reclaimable effective free capacity':'28GB','pool label':'LAB'},needed='reclaimable effective free capacity'),
 dict(id='rendering',task='Assess whether the synthetic renderer can finish the batch within60minutes.',facts='Batch:50 frames. Nominal speed:one frame/minute. All standard prerequisites have been provided. Recent jobs used unusually complex scenes.',sources={'representative scene duration':'two minutes/frame','renderer version':'LAB-2'},needed='representative scene duration'),
]
def log(row):
 with (P/'cpu-budget-v116-results.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
async def ctl(body):
 r,w=await asyncio.open_unix_connection(str(P/'cpu-control.sock'));w.write(json.dumps(body).encode()+b'\n');await w.drain();raw=await r.readline();w.close();await w.wait_closed();return json.loads(raw)
async def publish(text,revision):
 x=await ctl({'op':'withdraw'});generation=x['generation'];a=await ctl(dict(op='prepare',generation=generation,publication=text,revision=revision));assert a.get('state')=='prepared',a;b=await ctl(dict(op='refresh',generation=generation));assert b.get('state')=='active',b;return a

def query(body):
 t=time.time();r=urllib.request.Request(f'http://127.0.0.1:{PORT}/v1/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(r,timeout=240) as x:raw=json.loads(x.read())
 return raw,time.time()-t

def interpret(task,text,bindings):
 env=dict(os.environ,AIMEE_RESOLVER_ENDPOINT=f'http://127.0.0.1:{PORT}/v1/chat/completions',AIMEE_RESOLVER_MODEL=MODEL,AIMEE_RESOLVER_SCHEMA='1',AIMEE_RESOLVER_DISABLE_THINKING='1')
 row=json.dumps(dict(id=task['id'],task=task,text=text,view=dict(task=task,bindings=bindings)))+'\n';r=subprocess.run([str(P/'resolver-v112')],input=row,text=True,capture_output=True,env=env,timeout=240)
 return json.loads(r.stdout) if r.returncode==0 and r.stdout else dict(error=r.stderr or 'resolver process failed')
async def main():
 for case in CASES:
  for arm in ['native','ordinary-token-prefix']:
   for replicate in range(1):
    evidence=[];revisions=[];completion=False;discovered=False
    for turn in range(3):
     publication='Owner task: '+case['task']+'\n'+case['facts']+'\nOptional sources available to Aimee: '+', '.join(case['sources'])+'. If useful, request one source by its semantic name. Otherwise author your assessment. No operation has been performed.'+'\nOwner-resolved additional evidence: '+json.dumps(evidence)
     revision=f"{case['id']}-{arm}-{replicate}-{turn}";bank=await publish(publication,revision);revisions.append(revision)
     prefix=tok.encode(tok.apply_chat_template([dict(role='system',content='Authoritative memory:\n'+publication)],tokenize=False,add_generation_prompt=False,enable_thinking=False),add_special_tokens=False)
     cue='Read the owner task and resolved evidence. Ask Aimee for any additional information you need, or provide your authored assessment.'
     suffix=tok.encode(tok.apply_chat_template([dict(role='user',content=cue)],tokenize=False,add_generation_prompt=True,enable_thinking=False),add_special_tokens=False)
     body=dict(model=MODEL,prompt=suffix if arm=='native' else prefix+suffix,max_tokens=384,temperature=0,return_token_ids=True)
     if arm=='native':body['vllm_xargs']=dict(aimee_publication=revision)
     result,seconds=await asyncio.to_thread(query,body);text=result['choices'][0]['text'];finish=result['choices'][0]['finish_reason']
     source_root=P/'fixture-source-v112'/case['id'];source_root.mkdir(parents=True,exist_ok=True)
     bindings=[];capabilities=[];source_ids={}
     for index,(source,value) in enumerate(case['sources'].items()):
      cap='lookup-'+str(index);target=source_root/(cap+'.txt');target.write_text(value)
      source_ids[cap]=source
      capabilities.append(dict(id=cap,kinds=['need'],purpose='Obtain optional source: '+source+'. Select this only for a semantic request, including a paraphrase, not a statement that data already exists.',fields={}))
      bindings.append(dict(capability_id=cap,tool='read_file',arguments=dict(path=str(target)),fields={}))
     capabilities.append(dict(id='report',kinds=['content'],purpose='Authored assessment body; unsupported prior execution claims confer no permission.',fields=dict(body=dict(kind='text',required=True))))
     bindings.append(dict(capability_id='report',tool='write_file',arguments=dict(path=str(source_root/'assessment.txt')),fields=dict(body='content')))
     task=dict(id=case['id'],purpose=case['task'],capabilities=capabilities)
     resolved=await asyncio.to_thread(interpret,task,text,bindings) if finish=='stop' else dict(error='nonterminal contribution')
     intake=resolved.get('intake',{});decision=intake.get('decision',{});compiled=resolved.get('compiled');executed=None;effect=None
     if compiled and decision.get('kind')=='need' and decision.get('capability_id') in source_ids:
      source=source_ids[decision['capability_id']];expected=source_root/(decision['capability_id']+'.txt')
      if compiled['tool']=='read_file' and compiled['arguments']==dict(path=str(expected)) and source not in [e['source'] for e in evidence]:
       executed=dict(source=source,value=expected.read_text());evidence.append(executed);discovered=discovered or source==case['needed']
     elif compiled and decision.get('kind')=='content' and decision.get('capability_id')=='report':
      args=compiled['arguments'];target=source_root/'assessment.txt'
      if compiled['tool']=='write_file' and args.get('path')==str(target) and set(args)=={'path','content'}:
       target.write_text(args['content']);observed=target.read_text();completion=observed==args['content'];effect=dict(state='fixture_file_observed' if completion else 'unknown',sha256=hashlib.sha256(target.read_bytes()).hexdigest(),guard='research-fixture-not-enrolled',assessment_correctness='not_implied_by_file_write')
     metrics=await ctl({'op':'metrics'})
     log(dict(kind='turn',case=case['id'],arm=arm,replicate=replicate,turn=turn,publication=publication,bank=bank,request=body,response=result,seconds=seconds,owner_resolution=resolved,owner_executed_lookup=executed,metrics=metrics,ordinary_prompt_tokens=len(body['prompt']),private_prefix_tokens=len(prefix),oracle_used_only_for_scoring=dict(needed=case['needed'],discovered=discovered),compiled_file_effect=effect,qualified_completion=completion))
     if completion or executed is None:break
    log(dict(kind='episode',case=case['id'],arm=arm,replicate=replicate,additional_need_discovered=discovered,compiled_report=completion,owner_reads=evidence,revisions=revisions))
 log(dict(kind='terminal',result=await ctl({'op':'withdraw'})))
asyncio.run(main())
