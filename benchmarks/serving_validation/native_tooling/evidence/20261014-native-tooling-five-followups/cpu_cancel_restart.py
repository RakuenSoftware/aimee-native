import asyncio,json,urllib.request,time
from pathlib import Path
P=Path(__file__).parent;cfg=json.loads((P/'cpu-config.json').read_text());PORT=cfg['port'];MODEL=cfg['served_model_name']
async def ctl(body):
 r,w=await asyncio.open_unix_connection(str(P/'cpu-control.sock'));w.write(json.dumps(body).encode()+b'\n');await w.drain();raw=await r.readline();w.close();await w.wait_closed();return json.loads(raw)
async def main():
 x=await ctl({'op':'withdraw'});gen=x['generation'];prepared=await ctl(dict(op='prepare',generation=gen,publication='Owner task: author a long research report. Current synthetic display colour is jade. No recording has been performed.',revision='cancel-test'));assert prepared.get('state')=='prepared',prepared;assert (await ctl(dict(op='refresh',generation=gen))).get('state')=='active'
 body=dict(model=MODEL,messages=[dict(role='user',content='Write a detailed report about the current task.')],stream=True,max_tokens=512,temperature=0,chat_template_kwargs=dict(enable_thinking=False),vllm_xargs=dict(aimee_publication='cancel-test'))
 raw=json.dumps(body).encode();r,w=await asyncio.open_connection('127.0.0.1',PORT);w.write(f'POST /v1/chat/completions HTTP/1.1\r\nHost:127.0.0.1\r\nContent-Type:application/json\r\nContent-Length:{len(raw)}\r\n\r\n'.encode()+raw);await w.drain();received=b''
 while b'data:' not in received:
  chunk=await asyncio.wait_for(r.read(1024),240)
  if not chunk:break
  received+=chunk
 w.close();await w.wait_closed();await asyncio.sleep(1)
 row=dict(kind='disconnect',request=body,received=received.decode(errors='replace'),status=await ctl({'op':'status'}),metrics=await ctl({'op':'metrics'}))
 (P/'cpu-cancel-results.json').write_text(json.dumps(row,indent=2));print(json.dumps(row),flush=True)
asyncio.run(main())
