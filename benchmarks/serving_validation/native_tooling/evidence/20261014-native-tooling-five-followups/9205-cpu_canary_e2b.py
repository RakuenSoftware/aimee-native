import asyncio,json,urllib.request,time
from pathlib import Path
P=Path(__file__).parent;SOCKET=str(P/'cpu-control.sock');URL='http://127.0.0.1:8437/v1/chat/completions'
def append(name,value):
 with (P/name).open('a') as f:f.write(json.dumps(value)+'\n')
async def control(request):
 r,w=await asyncio.open_unix_connection(SOCKET);w.write(json.dumps(request).encode()+b'\n');await w.drain();response=json.loads(await r.readline());w.close();await w.wait_closed();append('canary-controls.jsonl',dict(request=request,response=response));return response
async def main():
 start=await control({'op':'withdraw'});generation=start['generation']
 pub='Task: report the current research display fact. Current resolved display colour is coral. Recording status: not performed. No display device was changed. Aimee-resolved contribution purpose: report the current colour and recording status.'
 prepared=await control(dict(op='prepare',generation=generation,publication=pub,revision='999'))
 assert prepared.get('state')=='prepared',prepared
 active=await control(dict(op='refresh',generation=generation));assert active.get('state')=='active',active
 body=dict(model='research-e2b-native',messages=[dict(role='user',content='Provide your current contribution for the bound task.')],max_tokens=128,temperature=0,chat_template_kwargs=dict(enable_thinking=False),vllm_xargs=dict(aimee_publication='999'))
 append('canary-requests.jsonl',body)
 def query():
  req=urllib.request.Request(URL,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'});t=time.time()
  with urllib.request.urlopen(req,timeout=180) as r:raw=r.read()
  append('canary-responses.jsonl',dict(raw=raw.decode(),seconds=time.time()-t));return json.loads(raw)
 result=await asyncio.to_thread(query);print(json.dumps(result),flush=True)
 metrics=await control({'op':'metrics'});assert metrics['workers'][0]['native_attention_reads']>0;assert metrics['workers'][0]['weights_unchanged'];print(json.dumps(metrics),flush=True)
asyncio.run(main())
