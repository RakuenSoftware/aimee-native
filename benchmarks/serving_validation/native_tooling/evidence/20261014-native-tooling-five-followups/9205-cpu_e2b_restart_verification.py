import asyncio,json,subprocess,time,urllib.request
from pathlib import Path
P=Path(__file__).parent
async def ctl(body):
 r,w=await asyncio.open_unix_connection(str(P/'cpu-control.sock'));w.write(json.dumps(body).encode()+b'\n');await w.drain();raw=await asyncio.wait_for(r.readline(),180);w.close();await w.wait_closed();return json.loads(raw)
async def main():
 cancelled=json.loads((P/'cpu-cancel-results.json').read_text());assert cancelled['status']['state']=='restart_required',cancelled['status']
 subprocess.run(['systemctl','restart','phase3-owner-v110-e2b-native'],check=True)
 for n in range(180):
  try:
   status=await ctl({'op':'status'})
   if status.get('state')=='paused':break
  except Exception:pass
  await asyncio.sleep(2)
 else:raise RuntimeError('owned CPU service did not restart ready')
 x=await ctl({'op':'withdraw'});g=x['generation'];a=await ctl(dict(op='prepare',generation=g,publication='Current synthetic display colour is cerulean.',revision='post-cancel-001'));assert a.get('state')=='prepared',a
 b=await ctl(dict(op='refresh',generation=g));assert b.get('state')=='active',b
 body=dict(model='research-e2b-native',messages=[dict(role='user',content='What is the current display colour? Answer with one word.')],max_tokens=32,temperature=0,chat_template_kwargs=dict(enable_thinking=False),vllm_xargs=dict(aimee_publication='post-cancel-001'))
 req=urllib.request.Request('http://127.0.0.1:8437/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=180) as r:response=json.loads(r.read())
 text=response['choices'][0]['message']['content'];correct='cerulean' in text.lower();row=dict(kind='terminal',cancel_state=cancelled['status'],restart_status=status,publication=a,request=body,response=response,correct=correct,metrics=await ctl({'op':'metrics'}),withdrawn=await ctl({'op':'withdraw'}));(P/'cpu-cancel-restart-verification.json').write_text(json.dumps(row,indent=2));assert correct,text
asyncio.run(main())
