import pathlib,subprocess,json,time,urllib.request,urllib.error,os
root=pathlib.Path('/opt/aimee-client/automatic-r1');report={'active_before':json.loads((root/'active.json').read_text()),'authority':'synthetic enrolled transport fixture; real signed installation and Gemma Q8 GPU; no harness-installed native banks or catalogs','checks':{}}
assert (root/'memory/catalog.json').exists(),'upgrade requires previous runtime state'
log=(root/'automatic-serve.log').open('w');server=subprocess.Popen(['/usr/local/bin/aimee-native-lab','--root',str(root),'run','--port','8111'],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
try:
 # Initially paused /health intentionally reports 503. The first authorized
 # request triggers selection, download and coordinated rank activation.
 deadline=time.time()+300
 while time.time()<deadline:
  if server.poll() is not None:raise RuntimeError('launcher exited; inspect serve log')
  try:
   with urllib.request.urlopen('http://127.0.0.1:8111/v1/models',timeout=5) as r:d=json.load(r)
   model=d['data'][0]['id'];break
  except (urllib.error.URLError,TimeoutError):time.sleep(1)
 else:raise RuntimeError('runtime startup timed out')
 request={'model':model,'messages':[{'role':'user','content':'Give the alpha vault code, alpha project name, and alpha drink. Answer all three briefly.'}],'temperature':0,'max_tokens':80,'chat_template_kwargs':{'enable_thinking':False}}
 for label in ['automatic_download_and_activation','cached_authenticated_selection']:
  start=time.perf_counter();r=urllib.request.Request('http://127.0.0.1:8111/v1/chat/completions',data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(r,timeout=180) as response:answer=json.load(response)
  text=answer['choices'][0]['message']['content'];assert all(s in text.lower() for s in ['68731','kestrel','rooibos']),answer
  cat=json.loads((root/'memory/catalog.json').read_text());assert len(cat['selections'][0]['records'])==3
  report['checks'][label]={'passed':True,'seconds':time.perf_counter()-start,'answer':text,'usage':answer['usage'],'selected_records':3}
 report['status']='passed'
finally:
 server.terminate()
 try:server.wait(timeout=40)
 except subprocess.TimeoutExpired:server.kill();server.wait()
 log.close();(root/('lifecycle-'+str(json.loads((root/'active.json').read_text())['current'][:12])+'.json')).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
