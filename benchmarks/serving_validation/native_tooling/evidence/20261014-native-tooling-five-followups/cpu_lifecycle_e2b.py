import asyncio,json,time,urllib.request,urllib.error,hashlib
from pathlib import Path
P=Path(__file__).parent
async def ctl(body):
 r,w=await asyncio.open_unix_connection(str(P/'cpu-control.sock'));w.write(json.dumps(body).encode()+b'\n');await w.drain();raw=await r.readline();w.close();await w.wait_closed();return json.loads(raw)
def query(body):
 t=time.time();req=urllib.request.Request('http://127.0.0.1:8437/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=180) as r:code=r.status;raw=r.read().decode()
 except urllib.error.HTTPError as e:code=e.code;raw=e.read().decode()
 return dict(status=code,response=json.loads(raw),seconds=time.time()-t)
def record(row):
 with (P/'cpu-lifecycle-results.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
async def main():
 revisions=['999','001','z','a','9','2'];colours=['coral','teal','amber','violet','silver','cyan']
 for revision,colour in zip(revisions,colours):
  withdrawn=await ctl({'op':'withdraw'});generation=withdrawn['generation'];record(dict(kind='withdraw',revision=revision,result=withdrawn))
  body=dict(model='research-e2b-native',messages=[dict(role='user',content='What is the current resolved display colour?')],max_tokens=24,temperature=0,chat_template_kwargs=dict(enable_thinking=False),vllm_xargs=dict(aimee_publication=revision))
  denied=await asyncio.to_thread(query,body);record(dict(kind='withdrawn-query',revision=revision,result=denied))
  bad=await ctl(dict(op='prepare',generation=generation-1,publication='bad generation',revision=revision));record(dict(kind='old-generation',result=bad))
  publication='Task: report the current resolved research display colour. Current resolved display colour is '+colour+'. No display device was changed.'
  prepared=await ctl(dict(op='prepare',generation=generation,publication=publication,revision=revision));record(dict(kind='prepare',revision=revision,result=prepared));assert prepared.get('state')=='prepared',prepared
  active=await ctl(dict(op='refresh',generation=generation));record(dict(kind='refresh',result=active));assert active.get('state')=='active',active
  for i in range(8):
   result=await asyncio.to_thread(query,body);record(dict(kind='decode',revision=revision,expected=colour,index=i,result=result))
  ordinary=dict(body);ordinary.pop('vllm_xargs');ordinary['messages']=[dict(role='user',content='Reply with the word ordinary.')]
  native_result,ordinary_result=await asyncio.gather(asyncio.to_thread(query,body),asyncio.to_thread(query,ordinary));record(dict(kind='mixed-batch',native=native_result,ordinary=ordinary_result,expected=colour))
  forged=dict(body);forged['vllm_xargs']=dict(aimee_cpu_capture='caller-controlled');record(dict(kind='capture-denial',result=await asyncio.to_thread(query,forged)))
  metrics=await ctl({'op':'metrics'});record(dict(kind='metrics',revision=revision,result=metrics));assert metrics['workers'][0]['weights_unchanged'],metrics
 record(dict(kind='terminal',result=await ctl({'op':'withdraw'})))
asyncio.run(main())
