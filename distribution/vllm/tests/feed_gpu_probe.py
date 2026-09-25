"""Actual publication stream + reader + preparation + GPU serving, lab authority.
Requires an isolated source/denial marker; never run against production memory.
"""
import argparse,json,os,pathlib,subprocess,time,urllib.request,urllib.error
p=argparse.ArgumentParser();p.add_argument('--root',default='/opt/aimee-memory-lab');p.add_argument('--output',required=True);a=p.parse_args()
root=pathlib.Path(a.root);fixture=root/'vllm-native-fixture-r1';build=root/'vllm-native-build';run=root/'feed-gpu-r1';run.mkdir(exist_ok=False)
source=json.loads((root/'selection-source-r4.json').read_text());denied=run/'denied';stream=run/'publication.sock';delivery=run/'delivered';children=[];logs=[];report={'authority':'same-UID authenticated Unix stream of synthetic approved records; not production Aimee account authentication'}
prep=json.loads((root/'real-reader-preparation-config.json').read_text());prep['memory_image']=str(delivery);(run/'preparation.json').write_text(json.dumps(prep))
config=json.loads((fixture/'onmiss-serving.json').read_text());config.update(start_paused=True,control_socket=str(run/'control.sock'),selection_socket=str(run/'selection.sock'),catalog=str(run/'catalog.json'));(run/'catalog.json').write_bytes((fixture/'onmiss-catalog.json').read_bytes());(run/'serving.json').write_text(json.dumps(config))
selector={k:prep[k] for k in ('image_reader','memory_image','authority','recipient','limit')};selector.update(catalog=config['catalog'],socket=config['selection_socket'],control_socket=config['control_socket'],preparation_config=str(run/'preparation.json'),native_prepare=str(build/'target/release/native-prepare'));(run/'selector.json').write_text(json.dumps(selector))
supervisor={'serving_config':str(run/'serving.json'),'server':[str(root/'vllm-env/bin/aimee-vllm'),'--config',str(run/'serving.json')],'follower':[str(root/'aimee-memory-image-release'),'follow-published','--publication-unix',str(stream),'--state-root',str(run/'cursor'),'--root',str(delivery)],'preparations':{'alpha':[str(build/'target/release/native-prepare'),str(run/'preparation.json')]},'restart_limit':1};(run/'supervisor.json').write_text(json.dumps(supervisor))
def spawn(command,label):
 log=open(a.output+'.'+label+'.log','w');logs.append(log);child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);children.append(child);return child
def request(name):
 query=f'{name} vault {name} project {name} drink: give my private vault code, project codename and preferred meeting drink.'
 payload={'model':config['model'],'messages':[{'role':'user','content':query}],'temperature':0,'max_tokens':96,'chat_template_kwargs':{'enable_thinking':False}}
 req=urllib.request.Request('http://127.0.0.1:8141/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 start=time.perf_counter()
 with urllib.request.urlopen(req,timeout=180) as r:result=json.load(r)
 text=result['choices'][0]['message']['content'];expected=['68731','kestrel','rooibos'] if name=='alpha' else ['94268','osprey','ginger']
 assert all(s in text.lower() for s in expected),result
 return {'text':text,'usage':result['usage'],'seconds':time.perf_counter()-start}
def eventually(name):
 deadline=time.monotonic()+300
 while time.monotonic()<deadline:
  if any(c.poll() is not None for c in children):raise RuntimeError('owned service exited')
  try:return request(name)
  except urllib.error.URLError:time.sleep(1)
 raise TimeoutError('activation timeout')
try:
 publisher=spawn([str(root/'aimee-publication-stream-fixture'),'--root',source['root'],'--socket',str(stream),'--denied',str(denied)],'publisher')
 spawn([str(root/'vllm-env/bin/python'),str(build/'distribution/service/selection.py'),'--config',str(run/'selector.json')],'selector')
 spawn([str(root/'vllm-env/bin/python'),str(build/'distribution/service/follow_native.py'),'--config',str(run/'supervisor.json')],'supervisor')
 report['initial']=eventually('alpha');report['prepared_on_miss']=request('beta');report['reused']=request('beta')
 catalog=json.loads((run/'catalog.json').read_text());assert all(len(s['records'])==3 for s in catalog['selections']);report['selected_records_per_bank']=[len(s['records']) for s in catalog['selections']]
 denied.touch();time.sleep(2)
 try:request('alpha');raise AssertionError('feed denial did not stop serving')
 except urllib.error.HTTPError as e:assert e.code==503;report['denial_status']=e.code
 denied.unlink();report['restored']=eventually('alpha')
 publisher.terminate();publisher.wait(timeout=10);time.sleep(2)
 try:request('alpha');raise AssertionError('lost feed did not stop admissions')
 except urllib.error.HTTPError as e:assert e.code==503;report['disconnected_status']=e.code
 report['status']='passed'
finally:
 for c in reversed(children):
  if c.poll() is None:
   c.terminate()
   try:c.wait(timeout=30)
   except subprocess.TimeoutExpired:os.killpg(c.pid,9);c.wait()
 for log in logs:log.close()
 pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
