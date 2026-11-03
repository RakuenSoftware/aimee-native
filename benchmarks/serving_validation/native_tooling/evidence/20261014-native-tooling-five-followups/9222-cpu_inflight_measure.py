import asyncio,json,time,urllib.request,urllib.error
from pathlib import Path
P=Path(__file__).parent;cfg=json.loads((P/'cpu-config.json').read_text());PORT=cfg['port'];MODEL=cfg['served_model_name']
async def ctl(body):
 r,w=await asyncio.open_unix_connection(str(P/'cpu-control.sock'));w.write(json.dumps(body).encode()+b'\n');await w.drain();raw=await r.readline();w.close();await w.wait_closed();return json.loads(raw)
def query(body):
 t=time.time();req=urllib.request.Request(f'http://127.0.0.1:{PORT}/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=240) as r:status=r.status;raw=r.read()
 except urllib.error.HTTPError as e:status=e.code;raw=e.read()
 return dict(status=status,response=json.loads(raw),seconds=time.time()-t)
def memory():
 unit='phase3-owner-v107-qwen-native-r5.service' if 'qwen' in MODEL else 'phase3-owner-v110-e2b-native.service'
 root=Path('/sys/fs/cgroup/system.slice')/unit
 return {name:int((root/name).read_text()) for name in ['memory.current','memory.peak'] if (root/name).exists()}
def record(row):
 with (P/'cpu-inflight-measure-results.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
async def main():
 x=await ctl({'op':'withdraw'});generation=x['generation'];pub='Owner task: report the current synthetic display colour. Current display colour is coral. No recording has happened.'
 prepared=await ctl(dict(op='prepare',generation=generation,publication=pub,revision='999-inflight'));assert prepared.get('state')=='prepared',prepared;assert (await ctl(dict(op='refresh',generation=generation))).get('state')=='active'
 body=dict(model=MODEL,messages=[dict(role='user',content='State the current display colour, then write a long description of colours.')],min_tokens=64,max_tokens=64,temperature=0,chat_template_kwargs=dict(enable_thinking=False),vllm_xargs=dict(aimee_publication='999-inflight'))
 task=asyncio.create_task(asyncio.to_thread(query,body));samples=[]
 for i in range(20):
  metrics=await ctl({'op':'metrics'});samples.append(dict(metrics=metrics,memory=memory(),time=time.time()))
  if metrics['active_requests']>0:break
  await asyncio.sleep(.1)
 withdrawn=await ctl({'op':'withdraw'});record(dict(kind='withdraw-inflight',request=body,prepared=prepared,withdrawn=withdrawn,samples=samples))
 denied=await asyncio.to_thread(query,body);record(dict(kind='new-request-after-withdraw',result=denied))
 generation=withdrawn['generation'];newpub='Owner task: report the current synthetic display colour. Current display colour is teal. No recording has happened.'
 preparing=asyncio.create_task(ctl(dict(op='prepare',generation=generation,publication=newpub,revision='001-inflight')))
 while not task.done():
  samples.append(dict(metrics=await ctl({'op':'metrics'}),memory=memory(),time=time.time()));await asyncio.sleep(.5)
 result=await task;next_bank=await preparing
 record(dict(kind='original-terminal',result=result,samples=samples,memory=memory(),next_prepare=next_bank))
 if next_bank.get('state')!='prepared':
  next_bank=await ctl(dict(op='prepare',generation=generation,publication=newpub,revision='001-inflight'));record(dict(kind='prepare-after-drain',result=next_bank))
 assert next_bank.get('state')=='prepared',next_bank
 active=await ctl(dict(op='refresh',generation=generation));assert active.get('state')=='active',active
 subsequent=dict(body);subsequent.pop('min_tokens');subsequent['max_tokens']=24;subsequent['messages']=[dict(role='user',content='What is the current resolved display colour?')];subsequent['vllm_xargs']=dict(aimee_publication='001-inflight')
 record(dict(kind='subsequent',result=await asyncio.to_thread(query,subsequent),metrics=await ctl({'op':'metrics'}),memory=memory()))
 record(dict(kind='terminal',result=await ctl({'op':'withdraw'})))
asyncio.run(main())
