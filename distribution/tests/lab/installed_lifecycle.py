"""Restart upgraded/rolled-back installed client on an isolated GPU host."""
import json,pathlib,subprocess,time,urllib.request
root=pathlib.Path('/opt/aimee-client');launcher=['/usr/local/bin/aimee-native-lab','--root',str(root)];report={}
def probe(label):
 log=open(root/(label+'.log'),'w');child=subprocess.Popen(launcher+['run','--port','8150'],stdout=log,stderr=subprocess.STDOUT)
 try:
  for _ in range(360):
   if child.poll() is not None:raise RuntimeError('installed runtime exited')
   try:
    with urllib.request.urlopen('http://127.0.0.1:8150/v1/models',timeout=2) as r:model=json.load(r)['data'][0]['id']
    break
   except Exception:time.sleep(1)
  else:raise TimeoutError('installed runtime startup')
  body={'model':model,'messages':[{'role':'user','content':'Give my private vault code, project codename and preferred meeting drink.'}],'temperature':0,'max_tokens':80,'chat_template_kwargs':{'enable_thinking':False},'vllm_xargs':{'aimee_publication':'alpha'}}
  request=urllib.request.Request('http://127.0.0.1:8150/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(request,timeout=120) as r:result=json.load(r)
  text=result['choices'][0]['message']['content'];assert all(v in text.lower() for v in ('68731','kestrel','rooibos')),result
  return {'model':model,'answer':text,'usage':result['usage'],'active':json.loads((root/'active.json').read_text())}
 finally:
  child.terminate()
  try:child.wait(timeout=45)
  except subprocess.TimeoutExpired:child.kill();child.wait()
  log.close()
try:
 report['upgrade']=probe('upgrade-serve');subprocess.run(launcher+['rollback'],check=True)
 report['rollback']=probe('rollback-serve')
 assert report['upgrade']['active']['current']!=report['rollback']['active']['current']
 assert report['rollback']['active']['high_water_sequence']==2
 report['status']='passed'
finally:(root/'installed-lifecycle.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
