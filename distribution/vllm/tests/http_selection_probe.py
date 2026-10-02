"""Actual scoped Go reader + automatic native HTTP selection; synthetic authority."""
import argparse,json,pathlib,subprocess,time,urllib.request,urllib.error
p=argparse.ArgumentParser();p.add_argument('--root',default='/opt/aimee-memory-lab');p.add_argument('--output',required=True);p.add_argument('--source',default='selection-source-r3.json');p.add_argument('--config',default='selection-serving.json');p.add_argument('--selector',default='selector.json');a=p.parse_args()
root=pathlib.Path(a.root);fixture=root/'vllm-native-fixture-r1';config=json.loads((fixture/a.config).read_text());source=json.loads((root/a.source).read_text());children=[];logs=[];report={}
def spawn(argv,label):
 log=open(a.output+'.'+label+'.log','w');logs.append(log);child=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT);children.append(child);return child
def request(name,forged=None):
 query=f'{name} vault, {name} project, {name} drink: give my private vault code, private project codename, and preferred meeting drink.'
 body={'model':config['model'],'messages':[{'role':'user','content':query}],'temperature':0,'max_tokens':96,'chat_template_kwargs':{'enable_thinking':False}}
 if forged:body['vllm_xargs']={'aimee_publication':forged}
 req=urllib.request.Request('http://127.0.0.1:8141/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=120) as r:out=json.load(r)
 text=out['choices'][0]['message']['content'].lower();expected=['68731','kestrel','rooibos'] if name=='alpha' else ['94268','osprey','ginger']
 assert all(v in text for v in expected),out
 return {'name':name,'forged_publication':forged,'text':text,'usage':out['usage']}
current=pathlib.Path(source['root'])/'CURRENT';hidden=current.with_name('CURRENT.probe-withdrawn')
try:
 spawn([str(root/'vllm-env/bin/python'),str(root/'vllm-native-build/distribution/service/selection.py'),'--config',str(fixture/a.selector)],'selector')
 spawn([str(root/'vllm-env/bin/aimee-vllm'),'--config',str(fixture/a.config)],'server')
 for _ in range(240):
  if any(c.poll() is not None for c in children):raise RuntimeError('service exited')
  try:
   with urllib.request.urlopen('http://127.0.0.1:8141/health',timeout=2):break
  except Exception:time.sleep(1)
 else:raise RuntimeError('startup timeout')
 report['answers']=[request('alpha'),request('beta'),request('alpha','beta')]
 current.rename(hidden)
 try:request('alpha','alpha');raise AssertionError('withdrawal bypassed')
 except urllib.error.HTTPError as e:assert e.code==503;report['withdrawal_status']=e.code
 hidden.rename(current);report['restored']=request('alpha');report['status']='passed'
finally:
 if hidden.exists():hidden.rename(current)
 for c in reversed(children):
  c.terminate()
  try:c.wait(timeout=30)
  except subprocess.TimeoutExpired:c.kill();c.wait()
 for log in logs:log.close()
 pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
