"""Concurrent serving isolation/pressure probe, not a knowledge benchmark."""
import argparse,concurrent.futures,json,pathlib,statistics,subprocess,time,urllib.request,urllib.error
p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--executable',required=True);p.add_argument('--output',required=True);p.add_argument('--requests',type=int,default=512);p.add_argument('--clients',type=int,default=8);a=p.parse_args()
c=json.loads(pathlib.Path(a.config).read_text());port=c['serve']['port'];base=f'http://127.0.0.1:{port}'
report={'requests':a.requests,'clients':a.clients,'rows':[],'fixture':'two three-record publications; repeated operational stress, not independent knowledge questions'}
log=open(a.output+'.server.log','w');child=subprocess.Popen([a.executable,'--config',a.config],stdout=log,stderr=subprocess.STDOUT)
def request(i):
 bank='alpha' if i%2==0 else 'beta';expected=['68731','kestrel','rooibos'] if bank=='alpha' else ['94268','osprey','ginger']
 body={'model':c['model'],'messages':[{'role':'user','content':'Give my private vault code, private project codename, and preferred meeting drink. Be concise.'}],'temperature':0,'max_tokens':80,'chat_template_kwargs':{'enable_thinking':False},'vllm_xargs':{'aimee_publication':bank}}
 start=time.perf_counter();rejections=0
 for attempt in range(200):
  try:
   req=urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
   with urllib.request.urlopen(req,timeout=180) as r:out=json.load(r)
   text=out['choices'][0]['message']['content'];return {'i':i,'bank':bank,'correct':all(w in text.lower() for w in expected),'text':text,'usage':out['usage'],'rejections':rejections,'elapsed_ms':(time.perf_counter()-start)*1000}
  except urllib.error.HTTPError as e:
   if e.code!=429:raise
   rejections+=1;time.sleep(max(float(e.headers.get('Retry-After','0')),min(.05*2**min(attempt,5),1.6))+(i%7)*.005)
 raise RuntimeError('admission retry budget exhausted')
try:
 for _ in range(240):
  if child.poll() is not None:raise RuntimeError('server exited')
  try:
   with urllib.request.urlopen(base+'/health',timeout=2):break
  except Exception:time.sleep(1)
 else:raise RuntimeError('startup timeout')
 request(0);request(1)
 start=time.perf_counter()
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.clients) as pool:
  for row in pool.map(request,range(a.requests)):report['rows'].append(row)
 report['seconds']=time.perf_counter()-start
 report['correct']=sum(r['correct'] for r in report['rows']);report['rejections']=sum(r['rejections'] for r in report['rows'])
 report['median_ms']=statistics.median(r['elapsed_ms'] for r in report['rows'])
 assert report['correct']==a.requests,report['correct']
finally:
 pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n');child.terminate()
 try:child.wait(timeout=30)
 except subprocess.TimeoutExpired:child.kill();child.wait()
 log.close()
print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
