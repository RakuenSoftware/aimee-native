"""Exact-image engineering certification on dedicated AMD GPUs.

Uses existing explicit synthetic prepared banks, never production permissions.
Runs matched answers, conversation growth, concurrent eviction pressure, streaming
TTFT and full-process/device measurements. Timing labels preserve their scope.
"""
import argparse,concurrent.futures,json,pathlib,socket,statistics,subprocess,threading,time,urllib.request,urllib.error
p=argparse.ArgumentParser();p.add_argument('--image',required=True);p.add_argument('--root',default='/opt/aimee-memory-lab');p.add_argument('--output',required=True);p.add_argument('--requests',type=int,default=128);p.add_argument('--profiles',nargs='+',choices=('bf16','q8'),default=['bf16','q8']);p.add_argument('--context-tokens',type=int,choices=(2048,8192),default=2048);p.add_argument('--gpu-utilization',type=float,default=.70);a=p.parse_args()
root=pathlib.Path(a.root);out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=False)
fixture=root/'vllm-native-fixture-r1';port=8160;base=f'http://127.0.0.1:{port}';name='aimee-image-certification'
report={'image':a.image,'image_inspect':json.loads(subprocess.check_output(['podman','image','inspect',a.image]))[0]['Id'],'scope':'synthetic operational certification; not population accuracy or live grant verification','profiles':{},'status':'running','context_tokens':a.context_tokens,'gpu_utilization':a.gpu_utilization}
stop=threading.Event();samples=[]
def sample():
 while not stop.is_set():
  devices={str(f):int(f.read_text()) for f in pathlib.Path('/sys/class/drm').glob('card*/device/mem_info_vram_used')}
  samples.append({'monotonic_ns':time.monotonic_ns(),'device_used_bytes':devices});stop.wait(.2)
thread=threading.Thread(target=sample,daemon=True);thread.start()
def save():
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 (out/'device-samples.json').write_text(json.dumps(samples)+'\n')
def control(path):
 with socket.socket(socket.AF_UNIX) as s:
  s.settimeout(40);s.connect(str(path));s.sendall(b'{"op":"metrics"}\n');f=s.makefile('rb');result=json.loads(f.readline())
 if 'error' in result:raise RuntimeError(result)
 return result

def request(payload,stream=False):
 body=dict(payload)
 if stream:body.update(stream=True,stream_options={'include_usage':True})
 start=time.perf_counter_ns();first=None;text='';usage=None
 req=urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=180) as response:
  if not stream:
   result=json.load(response);text=result['choices'][0]['message']['content'];usage=result['usage']
  else:
   for line in response:
    if not line.startswith(b'data: '):continue
    chunk=line[6:].strip()
    if chunk==b'[DONE]':break
    value=json.loads(chunk)
    if value.get('usage'):usage=value['usage']
    for choice in value.get('choices',[]):
     content=choice.get('delta',{}).get('content') or ''
     if content and first is None:first=time.perf_counter_ns()
     text+=content
 end=time.perf_counter_ns()
 return {'answer':text,'usage':usage,'request_ms':(end-start)/1e6,'ttft_ms':None if first is None else (first-start)/1e6,'after_first_ms':None if first is None else (end-first)/1e6}

def payload(model,bank='alpha',mode='native',turns=0):
 values=('68731','Kestrel','rooibos') if bank=='alpha' else ('94268','Osprey','ginger tea')
 messages=[]
 if mode=='text':messages.append({'role':'system','content':f"Authoritative memory:\nThe user's private vault code is {values[0]}.\nThe user's private project codename is {values[1]}.\nThe user's preferred meeting drink is {values[2]}."})
 for _ in range(turns):messages.extend([{'role':'user','content':'We are planning a meeting.'},{'role':'assistant','content':'Understood.'}])
 messages.append({'role':'user','content':'Give my private vault code, private project codename, and preferred meeting drink. Reply with only those three values.'})
 result={'model':model,'messages':messages,'temperature':0,'max_tokens':80,'chat_template_kwargs':{'enable_thinking':False}}
 if mode=='native':result['vllm_xargs']={'aimee_publication':bank}
 return result,values

def long_payload(model,bank,mode,target):
 body,expected=payload(model,bank,mode)
 question=body['messages'][-1]['content']
 def count(repeats):
  body['messages'][-1]['content']='Background meeting notes:\n'+('meeting agenda. '*repeats)+'\n\n'+question
  req=urllib.request.Request(base+'/tokenize',data=json.dumps({'model':model,'messages':body['messages'],'chat_template_kwargs':{'enable_thinking':False}}).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)['count']
 low,high=0,target
 if count(high)<target:raise RuntimeError('long-context fixture cannot reach target')
 while low<high:
  mid=(low+high)//2
  if count(mid)<target:low=mid+1
  else:high=mid
 actual=count(low)
 if not target<=actual<a.context_tokens-body['max_tokens']:raise RuntimeError('long-context fixture outside context budget')
 return body,expected,actual

try:
 for profile in a.profiles:
  work=out/profile;work.mkdir();sock=work/'control.sock'
  config=json.loads((fixture/'disk-config.json').read_text())
  config.update(library='/opt/aimee/libaimee_native.so',device_memory_budget=10*1024**2,control_socket=str(sock),serve={'tensor_parallel_size':2,'port':port,'gpu_memory_utilization':a.gpu_utilization,'max_model_len':a.context_tokens,'max_num_seqs':4,'max_num_batched_tokens':256})
  if profile=='q8':config['gguf_weights']=str(root/'gemma4-aimee-q8.gguf')
  (work/'config.json').write_text(json.dumps(config))
  cmd=['podman','run','--rm','--name',name,'--network','host','--ipc','host','--device','/dev/kfd','--device','/dev/dri/renderD128','--device','/dev/dri/renderD129','--memory','48g','--memory-swap','48g','-v',f'{fixture}:{fixture}:ro','-v',f'{root}/gemma4:{root}/gemma4:ro','-v',f'{work}:{work}:rw']
  if profile=='q8':cmd+=['-v',f'{root}/gemma4-aimee-q8.gguf:{root}/gemma4-aimee-q8.gguf:ro']
  cmd += [a.image,'--config',str(work/'config.json')]
  log=(work/'server.log').open('w');child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
  data={'status':'starting','metrics':{},'streaming':[],'concurrency':[]};report['profiles'][profile]=data;save()
  def metrics(label):
   data['metrics'][label]={'workers':control(sock),'cgroup':subprocess.check_output(['podman','exec',name,'sh','-c','cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.peak /sys/fs/cgroup/memory.max'],text=True).splitlines()}
  try:
   for _ in range(360):
    if child.poll() is not None:raise RuntimeError('runtime exited; inspect server log')
    try:
     with urllib.request.urlopen(base+'/health',timeout=2):break
    except (urllib.error.URLError,TimeoutError):time.sleep(1)
   else:raise TimeoutError('startup')
   with urllib.request.urlopen(base+'/v1/models') as r:model=json.load(r)['data'][0]['id']
   metrics('loaded')
   subprocess.run(['python3',str(pathlib.Path(__file__).with_name('serving_matrix.py')),'--endpoint',base,'--output',str(work/'matrix.json'),'--label',profile+'-exact-image'],check=True)
   matrix=json.loads((work/'matrix.json').read_text());data['matrix_summary']=matrix['summary'];assert all(r['correct'] for r in matrix['rows'])
   metrics('after_matrix');save()
   data['long_context']=[]
   if a.context_tokens==8192:
    for target in (4096,7168):
     for bank in ('alpha','beta'):
      for mode in ('native','text'):
       body,expected,actual=long_payload(model,bank,mode,target)
       row=request(body);row.update(target_prompt_tokens=target,tokenized_prompt_tokens=actual,bank=bank,mode=mode,correct=all(v.lower() in row['answer'].lower() for v in expected))
       data['long_context'].append(row);save()
       assert row['usage']['prompt_tokens']==actual,'tokenizer and inference disagree'
       assert row['correct'],'long-context memory recall failed'
    metrics('after_long_context');save()
   def concurrent_request(i):
    bank='alpha' if i%2==0 else 'beta';body,expected=payload(model,bank)
    retries=0;started=time.perf_counter()
    for attempt in range(200):
     try:
      row=request(body);row.update(i=i,bank=bank,retries=retries,correct=all(v.lower() in row['answer'].lower() for v in expected),total_with_retries_ms=(time.perf_counter()-started)*1000);return row
     except urllib.error.HTTPError as e:
      if e.code!=429:raise
      retries+=1;time.sleep(max(float(e.headers.get('Retry-After','0')),min(.05*2**min(attempt,5),1.6))+(i%7)*.005)
    raise RuntimeError('retry budget exhausted')
   with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    for row in pool.map(concurrent_request,range(a.requests)):data['concurrency'].append(row)
   assert all(row['correct'] for row in data['concurrency']);metrics('after_concurrency');save()
   for i in range(20):
    for mode in (('native','text') if i%2==0 else ('text','native')):
     body,expected=payload(model,mode=mode,turns=48 if i>=10 else 0)
     row=request(body,stream=True);row.update(mode=mode,turns=48 if i>=10 else 0,correct=all(v.lower() in row['answer'].lower() for v in expected));data['streaming'].append(row)
   assert all(row['correct'] for row in data['streaming']);metrics('after_streaming')
   data['status']='passed';save()
  finally:
   subprocess.run(['podman','stop','--time','30',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   child.wait(timeout=45);log.close()
 report['status']='passed'
except BaseException as e:
 report['status']='failed';report['error']=str(e);raise
finally:
 stop.set();thread.join(timeout=5);save()
print(json.dumps({'status':report['status'],'image':report['image_inspect'],'profiles':{k:v['status'] for k,v in report['profiles'].items()}}))
