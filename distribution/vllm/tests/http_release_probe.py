"""Packaged HTTP control and paired native/text serving probe; synthetic records."""
import argparse,asyncio,json,os,pathlib,statistics,subprocess,time,urllib.request,urllib.error
p=argparse.ArgumentParser();p.add_argument('--lab-root',default='/opt/aimee-memory-lab');p.add_argument('--output',required=True);a=p.parse_args()
root=pathlib.Path(a.lab_root);fixture=root/'vllm-native-fixture-r1';config=json.loads((fixture/'config.json').read_text())
config['serve']={'tensor_parallel_size':2,'port':8137};config['control_socket']=str(fixture/'control.sock')
path=fixture/'release-serve.json';path.write_text(json.dumps(config));catalog=pathlib.Path(config['catalog']);original=catalog.read_text()
log=open('/tmp/aimee-release-http.log','w')
child=subprocess.Popen([str(root/'vllm-env/bin/aimee-vllm'),'--config',str(path)],stdout=log,stderr=subprocess.STDOUT)
async def ctl(op):
 r,w=await asyncio.open_unix_connection(config['control_socket']);w.write(json.dumps({'op':op}).encode()+b'\n');await w.drain()
 result=json.loads(await asyncio.wait_for(r.readline(),120));w.close();await w.wait_closed();return result
def request(condition,turns=0):
 messages=[]
 if condition=='text':messages.append({'role':'system','content':"Authoritative memory:\nThe user's private vault code is 68731.\nThe user's private project codename is Kestrel.\nThe user's preferred meeting drink is rooibos."})
 for _ in range(turns):messages.extend([{'role':'user','content':'We are planning a meeting.'},{'role':'assistant','content':'Understood.'}])
 messages.append({'role':'user','content':'What is my private vault code? Reply with the code only.'})
 payload={'model':config['model'],'messages':messages,'temperature':0,'max_tokens':24,'chat_template_kwargs':{'enable_thinking':False}}
 if condition=='native':payload['vllm_xargs']={'aimee_publication':'alpha'}
 req=urllib.request.Request('http://127.0.0.1:8137/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 start=time.perf_counter_ns()
 with urllib.request.urlopen(req,timeout=120) as response:result=json.load(response)
 return {'condition':condition,'turns':turns,'elapsed_ms':(time.perf_counter_ns()-start)/1e6,'text':result['choices'][0]['message']['content'],'usage':result['usage']}
report={}
try:
 for _ in range(180):
  if child.poll() is not None:raise RuntimeError('server exited')
  try:
   with urllib.request.urlopen('http://127.0.0.1:8137/health',timeout=2):break
  except Exception:time.sleep(1)
 else:raise RuntimeError('startup timeout')
 report['initial']=request('native')
 changed=json.loads(original);changed['publications']['alpha']=changed['publications']['beta'];stage=catalog.with_suffix('.next');stage.write_text(json.dumps(changed));stage.replace(catalog)
 report['refresh']=asyncio.run(ctl('refresh'));assert report['refresh'].get('state')=='active',report
 report['replacement']=request('native');assert '94268' in report['replacement']['text']
 stage=catalog.with_suffix('.next');stage.write_text(original);stage.replace(catalog);assert asyncio.run(ctl('refresh'))['state']=='active'
 report['withdraw']=asyncio.run(ctl('withdraw'))
 try:request('native');raise AssertionError('withdrawal did not stop admission')
 except urllib.error.HTTPError as e:assert e.code==503;report['withdraw_http_status']=e.code
 assert asyncio.run(ctl('refresh'))['state']=='active'
 rows=[]
 for turns in [0,16,48]:
  # Warm each shape before paired measurements; no text prefix caching enabled.
  request('native',turns);request('text',turns)
  for repeat in range(5):
   for condition in (['native','text'] if repeat%2==0 else ['text','native']):rows.append(request(condition,turns))
 report['rows']=rows;report['summary']=[]
 for turns in [0,16,48]:
  for condition in ['native','text']:
   subset=[r for r in rows if r['turns']==turns and r['condition']==condition]
   report['summary'].append({'turns':turns,'condition':condition,'n':len(subset),'median_ms':statistics.median(r['elapsed_ms'] for r in subset),'correct':sum('68731' in r['text'] for r in subset),'prompt_tokens':sorted({r['usage']['prompt_tokens'] for r in subset})})
finally:
 stage=catalog.with_suffix('.next');stage.write_text(original);stage.replace(catalog)
 pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
 child.terminate()
 try:child.wait(timeout=30)
 except subprocess.TimeoutExpired:child.kill();child.wait()
print(json.dumps(report.get('summary',report)),flush=True)
