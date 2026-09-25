"""32-record native working-set certification, actual scoped reader/compiler.
Synthetic authority. All 32 selected records are encoded in one active bank.
"""
import argparse,hashlib,json,os,pathlib,random,re,subprocess,time,urllib.request
p=argparse.ArgumentParser();p.add_argument('--root',default='/opt/aimee-memory-lab');p.add_argument('--output',required=True);p.add_argument('--run-name',default='wide-native-r1');p.add_argument('--resume',action='store_true');a=p.parse_args()
root=pathlib.Path(a.root);build=root/'vllm-native-build';work=root/a.run_name;work.mkdir(exist_ok=a.resume)
codes=random.Random(20260925).sample(range(10000,100000),32)
facts=[{'cue':f'unit {i:03d}','content':f'The access code for unit {i:03d} is {code}.'} for i,code in enumerate(codes)]
if a.resume:
 assert json.loads((work/'facts.json').read_text())==facts
 prep=json.loads((work/'preparation.json').read_text())
 assert prep['query']==' '.join(f['cue'] for f in facts) and prep['limit']==32
else:
 (work/'facts.json').write_text(json.dumps(facts));source=json.loads(subprocess.check_output([str(root/'aimee-selection-fixture-wide'),'--root',str(work/'source'),'--facts',str(work/'facts.json')]))
 prep=json.loads((root/'real-reader-preparation-config.json').read_text());prep.update(memory_image=source['root'],query=' '.join(f['cue'] for f in facts),limit=32,encoding_revision='wide-working-set-v1',host_memory_budget=512*1024**2)
(work/'preparation.json').write_text(json.dumps(prep));start=time.perf_counter();prepared=json.loads(subprocess.check_output([str(build/'target/release/native-prepare'),str(work/'preparation.json')]))
assert len(prepared['records'])==32,prepared
bank=pathlib.Path(prepared['root']);index=json.loads((bank/'index.json').read_text());report={'authority':'synthetic 32-record scoped source, actual reader and CPU compiler','preparation_seconds':time.perf_counter()-start,'preparation_reused':prepared['reused'],'selected_records':prepared['records'],'payload_bytes':(bank/'compact.pack').stat().st_size,'rows':[]}
catalog={'recipient':'synthetic-validation','model_config_sha256':hashlib.sha256((root/'gemma4/config.json').read_bytes()).hexdigest(),'publications':{'wide':{k:prepared[k] for k in ('root','model','key')}}};(work/'catalog.json').write_text(json.dumps(catalog))
config={'catalog':str(work/'catalog.json'),'recipient':'synthetic-validation','model':str(root/'gemma4'),'gguf_weights':str(root/'gemma4-aimee-q8.gguf'),'library':str(build/'target/release/libaimee_qwen.so'),'host_memory_budget':512*1024**2,'disk_backed':True,'serve':{'tensor_parallel_size':2,'port':8152}}
(work/'serving.json').write_text(json.dumps(config));log=open(a.output+'.server.log','w');child=subprocess.Popen([str(root/'vllm-env/bin/aimee-vllm'),'--config',str(work/'serving.json')],stdout=log,stderr=subprocess.STDOUT)
try:
 for _ in range(300):
  if child.poll() is not None:raise RuntimeError('wide runtime exited')
  try:
   with urllib.request.urlopen('http://127.0.0.1:8152/health',timeout=2):break
  except Exception:time.sleep(1)
 else:raise TimeoutError('wide runtime startup')
 groups=[(i,) for i in range(32)]+[(i,31-i) for i in range(16)]+[(i,i+8,i+16) for i in range(8)]
 for number,group in enumerate(groups):
  question='Give the access codes for '+', '.join(f'unit {i:03d}' for i in group)+'. Reply with only the codes.'
  for mode in (('native','text') if number%2==0 else ('text','native')):
   messages=[]
   if mode=='text':messages.append({'role':'system','content':'Authoritative memory:\n'+'\n'.join(f['content'] for f in facts)})
   messages.append({'role':'user','content':question})
   payload={'model':config['model'],'messages':messages,'temperature':0,'max_tokens':64,'chat_template_kwargs':{'enable_thinking':False}}
   if mode=='native':payload['vllm_xargs']={'aimee_publication':'wide'}
   req=urllib.request.Request('http://127.0.0.1:8152/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
   start=time.perf_counter()
   with urllib.request.urlopen(req,timeout=180) as r:result=json.load(r)
   answer=result['choices'][0]['message']['content'];expected=[str(codes[i]) for i in group];actual=re.findall(r'\b\d{5}\b',answer)
   report['rows'].append({'mode':mode,'records_queried':list(group),'expected':expected,'actual_codes':actual,'answer':answer,'correct':sorted(actual)==sorted(expected),'usage':result['usage'],'seconds':time.perf_counter()-start})
   pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
 report['summary']=[{'mode':mode,'n':sum(r['mode']==mode for r in report['rows']),'correct':sum(r['correct'] for r in report['rows'] if r['mode']==mode)} for mode in ('native','text')]
 report['status']='completed'
finally:
 child.terminate()
 try:child.wait(timeout=45)
 except subprocess.TimeoutExpired:child.kill();child.wait()
 log.close();pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)
