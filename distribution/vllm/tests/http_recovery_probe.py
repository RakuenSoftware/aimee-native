"""GPU HTTP interruption/restart probe; synthetic local publication authority."""
import argparse, asyncio, json, os, pathlib, subprocess, time, urllib.request, urllib.error
p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--executable',required=True);p.add_argument('--output',required=True);a=p.parse_args()
original=json.loads(pathlib.Path(a.config).read_text());root=pathlib.Path(a.output).parent
c=dict(original);c['serve']={'tensor_parallel_size':2,'port':8140};c['start_paused']=True;c['control_socket']=str(root/'recovery.sock')
path=root/'recovery-serving.json';path.write_text(json.dumps(c));base='http://127.0.0.1:8140';report={};child=None;log=None
async def control(request):
 r,w=await asyncio.wait_for(asyncio.open_unix_connection(c['control_socket']),5)
 try:
  w.write(json.dumps(request).encode()+b'\n');await w.drain()
  return json.loads(await asyncio.wait_for(r.readline(),120))
 finally:w.close();await w.wait_closed()
def ctl(op,**kw):return asyncio.run(control({'op':op,**kw}))
def request(stream=False):
 query='Write a numbered list of 200 imaginary meeting ideas, with a sentence for each.' if stream else 'What is my private vault code? Reply with the code only.'
 body={'model':c['model'],'messages':[{'role':'user','content':query}],'temperature':0,'max_tokens':1024 if stream else 24,'stream':stream,'chat_template_kwargs':{'enable_thinking':False},'vllm_xargs':{'aimee_publication':'alpha'}}
 return urllib.request.urlopen(urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=120)
def expect_closed():
 try:
  with request():pass
  raise AssertionError('admission unexpectedly open')
 except urllib.error.HTTPError as e:assert e.code==503,e.code
def stop():
 global child,log
 if child is not None:
  child.terminate()
  try:child.wait(timeout=30)
  except subprocess.TimeoutExpired:child.kill();child.wait()
  child=None
 if log is not None:log.close();log=None
 # Test owns this single server endpoint; process has exited before cleanup.
 pathlib.Path(c['control_socket']).unlink(missing_ok=True)
def start(round):
 global child,log
 log=open(a.output+f'.server-{round}.log','w')
 child=subprocess.Popen([a.executable,'--config',str(path)],stdout=log,stderr=subprocess.STDOUT)
 for _ in range(240):
  if child.poll() is not None:raise RuntimeError('serving exited during startup')
  try:
   status=ctl('status')
   if status.get('state')=='paused':return
  except (OSError,asyncio.TimeoutError):pass
  time.sleep(1)
 raise RuntimeError('startup timeout')
try:
 start(1);expect_closed();report['initial_admission']='closed'
 first=ctl('withdraw');second=ctl('withdraw')
 report['superseded']=ctl('refresh',generation=first['generation']);assert 'error' in report['superseded'];expect_closed()
 report['activation']=ctl('refresh',generation=second['generation']);assert report['activation']['state']=='active'
 with request() as r:report['before_cancel']=json.load(r)
 assert '68731' in report['before_cancel']['choices'][0]['message']['content']
 with request(True) as r:
  # Close after actual generated content, while a long output is still active.
  for _ in range(100):
   line=r.readline()
   if line.startswith(b'data: ') and line.strip()!=b'data: [DONE]':
    event=json.loads(line[6:])
    if event.get('choices',[{}])[0].get('delta',{}).get('content'):
     report['cancelled_after_content']=True;break
  else:raise AssertionError('no generated content to interrupt')
 for _ in range(100):
  status=ctl('status')
  if status.get('state')=='restart_required':break
  time.sleep(.1)
 else:raise AssertionError(f'interruption did not close admission: {status}')
 expect_closed();report['after_cancel']=status
 stop();start(2);expect_closed();report['restart_admission']='closed'
 report['old_generation_after_restart']=ctl('refresh',generation=second['generation']);assert 'error' in report['old_generation_after_restart']
 fresh=ctl('withdraw');report['reactivation']=ctl('refresh',generation=fresh['generation']);assert report['reactivation']['state']=='active'
 with request() as r:report['after_restart']=json.load(r)
 assert '68731' in report['after_restart']['choices'][0]['message']['content']
 report['status']='passed'
finally:
 stop();pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('before_cancel','after_restart')}))
