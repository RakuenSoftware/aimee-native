"""Reconsume the verified 32-record prepared fixture using an exact client image.
No fresh authorization or preparation timing is claimed by this engine test.
"""
import argparse,hashlib,json,pathlib,re,socket,subprocess,time,urllib.request,urllib.error
p=argparse.ArgumentParser();p.add_argument('--image',required=True);p.add_argument('--root',default='/opt/aimee-memory-lab');p.add_argument('--output',required=True);a=p.parse_args()
root=pathlib.Path(a.root);work=pathlib.Path(a.output);work.mkdir(parents=True,exist_ok=False)
fixture=root/'wide-native-r2';catalog=json.loads((fixture/'catalog.json').read_text());spec=catalog['publications']['wide'];bank=pathlib.Path(spec['root']);identity=json.loads((bank.parent/'identity.json').read_text());facts=json.loads((fixture/'facts.json').read_text())
assert len(identity['records'])==len(facts)==32
assert identity['model_revision']==spec['model'] and identity['recipient']==catalog['recipient']
assert hashlib.sha256((root/'gemma4/config.json').read_bytes()).hexdigest()==catalog['model_config_sha256']
(work/'catalog.json').write_text(json.dumps(catalog));control=work/'control.sock'
config={'catalog':str(work/'catalog.json'),'recipient':catalog['recipient'],'model':str(root/'gemma4'),'gguf_weights':str(root/'gemma4-aimee-q8.gguf'),'library':'/opt/aimee/libaimee_native.so','host_memory_budget':512*1024**2,'device_memory_budget':256*1024**2,'disk_backed':True,'control_socket':str(control),'serve':{'tensor_parallel_size':2,'port':8161,'gpu_memory_utilization':.70}}
(work/'config.json').write_text(json.dumps(config));report={'status':'running','image':json.loads(subprocess.check_output(['podman','image','inspect',a.image]))[0]['Id'],'selected_records':identity['records'],'bank_sha256':hashlib.file_digest((bank/'compact.pack').open('rb'),'sha256').hexdigest(),'payload_bytes':(bank/'compact.pack').stat().st_size,'scope':'previously authorized synthetic engineering fixture; all 32 records encoded together; no live authorization/preparation timing claim','rows':[]}
cmd=['podman','run','--rm','--name','aimee-wide-certification','--network','host','--ipc','host','--device','/dev/kfd','--device','/dev/dri/renderD128','--device','/dev/dri/renderD129','--memory','48g','--memory-swap','48g']
for path,mode in [(root/'gemma4','ro'),(root/'gemma4-aimee-q8.gguf','ro'),(bank,'ro'),(work,'rw')]:cmd+=['-v',f'{path}:{path}:{mode}']
cmd += [a.image,'--config',str(work/'config.json')]
log=(work/'server.log').open('w');child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
def save():(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
try:
 for _ in range(360):
  if child.poll() is not None:raise RuntimeError('wide runtime exited')
  try:
   with urllib.request.urlopen('http://127.0.0.1:8161/health',timeout=2):break
  except (urllib.error.URLError,TimeoutError):time.sleep(1)
 else:raise TimeoutError('startup')
 groups=[(i,) for i in range(32)]+[(i,31-i) for i in range(16)]+[(i,i+8,i+16) for i in range(8)]
 for number,group in enumerate(groups):
  question='Give the access codes for '+', '.join(f'unit {i:03d}' for i in group)+'. Reply with only the codes.'
  for mode in (('native','text') if number%2==0 else ('text','native')):
   messages=[]
   if mode=='text':messages.append({'role':'system','content':'Authoritative memory:\n'+'\n'.join(f['content'] for f in facts)})
   messages.append({'role':'user','content':question})
   payload={'model':config['model'],'messages':messages,'temperature':0,'max_tokens':64,'chat_template_kwargs':{'enable_thinking':False}}
   if mode=='native':payload['vllm_xargs']={'aimee_publication':'wide'}
   req=urllib.request.Request('http://127.0.0.1:8161/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
   start=time.perf_counter()
   with urllib.request.urlopen(req,timeout=180) as r:answer=json.load(r)
   text=answer['choices'][0]['message']['content'];actual=re.findall(r'\b\d{5}\b',text);expected=[re.findall(r'\b\d{5}\b',facts[i]['content'])[0] for i in group]
   report['rows'].append({'mode':mode,'records_queried':list(group),'correct':sorted(actual)==sorted(expected),'answer':text,'expected':expected,'usage':answer['usage'],'request_ms':(time.perf_counter()-start)*1000});save()
 with socket.socket(socket.AF_UNIX) as s:
  s.settimeout(40);s.connect(str(control));s.sendall(b'{"op":"metrics"}\n');report['metrics']=json.loads(s.makefile('rb').readline())
 assert len(report['metrics']['workers'])==2
 assert all(r['correct'] for r in report['rows'])
 report['status']='passed'
except BaseException as e:report['status']='failed';report['error']=str(e);raise
finally:
 save();subprocess.run(['podman','stop','--time','30','aimee-wide-certification'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);child.wait(timeout=45);log.close()
print(json.dumps({'status':report['status'],'answers':len(report['rows'])}))
