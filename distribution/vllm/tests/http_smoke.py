import hashlib,base64,importlib.metadata,json,os,pathlib,subprocess,time,urllib.request
# Lab integration check; uses only synthetic publications.
import argparse
p=argparse.ArgumentParser();p.add_argument('--lab-root',default='/opt/aimee-memory-lab');a=p.parse_args()
root=pathlib.Path(a.lab_root)
# Check all RECORD-hashed upstream files against the installed wheel.
dist=importlib.metadata.distribution('vllm');checked=0;changed=[]
for item in dist.files:
 if item.hash and item.hash.mode=='sha256':
  actual=base64.urlsafe_b64encode(hashlib.sha256(item.locate().read_bytes()).digest()).rstrip(b'=').decode()
  checked+=1
  if actual!=item.hash.value:changed.append(str(item))
assert not changed,changed
fixture=root/'vllm-native-fixture-r1'
config=json.loads((fixture/'config.json').read_text());config['serve']={'tensor_parallel_size':2,'port':8137}
p=(fixture/'serve.json');p.write_text(json.dumps(config))
log=open('/tmp/aimee-vllm-http.log','w')
child=subprocess.Popen([str(root/'vllm-env/bin/python'),'-m','aimee_vllm.cli','--config',str(p)],stdout=log,stderr=subprocess.STDOUT)
try:
 for i in range(180):
  if child.poll() is not None:raise RuntimeError('server exited; inspect HTTP log')
  try:
   with urllib.request.urlopen('http://127.0.0.1:8137/health',timeout=2):break
  except Exception:time.sleep(1)
 else:raise RuntimeError('server startup timed out')
 rows=[]
 for cond in ['alpha','beta']:
  payload={'model':config['model'],'messages':[{'role':'user','content':'What is my private vault code? Reply with the code only.'}],'temperature':0,'max_tokens':32,'chat_template_kwargs':{'enable_thinking':False},'vllm_xargs':{'aimee_publication':cond}}
  req=urllib.request.Request('http://127.0.0.1:8137/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=90) as response: data=json.load(response)
  rows.append({'publication':cond,'text':data['choices'][0]['message']['content'],'usage':data['usage']})
 report={'upstream_record_files_checked':checked,'upstream_files_modified':changed,'rows':rows}
 (fixture/'http.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
 assert '68731' in rows[0]['text'] and '94268' in rows[1]['text']
 assert rows[0]['usage']['prompt_tokens']==rows[1]['usage']['prompt_tokens']
finally:
 child.terminate()
 try:child.wait(timeout=30)
 except subprocess.TimeoutExpired:child.kill();child.wait()
