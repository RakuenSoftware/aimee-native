"""Operator probe: refresh while a real long generation owns admission."""
import argparse,concurrent.futures,json,pathlib,socket,time,urllib.request,urllib.error
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--socket',required=True);p.add_argument('--endpoint',default='http://127.0.0.1:8170');a=p.parse_args()
out=pathlib.Path(a.output)
if out.exists():raise ValueError('preserve existing probe')
report={'status':'running','scope':'Real long-generation drain and admission recovery; not a task accuracy measurement'}
def save():out.write_text(json.dumps(report,indent=2)+'\n')
def api(path,body=None):
 req=urllib.request.Request(a.endpoint+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=660) as r:return json.load(r)
def control(op):
 with socket.socket(socket.AF_UNIX) as s:
  s.settimeout(660);s.connect(a.socket);s.sendall(json.dumps({'op':op}).encode()+b'\n');return json.loads(s.makefile('rb').readline())
def generation(body):
 start=time.monotonic();r=api('/v1/chat/completions',body);return {'seconds':time.monotonic()-start,'response':r}
def refresh():
 start=time.monotonic();r=control('refresh');return {'seconds':time.monotonic()-start,'result':r}
save()
try:
 for _ in range(240):
  try:
   with urllib.request.urlopen(a.endpoint+'/health',timeout=2):break
  except (urllib.error.URLError,TimeoutError):time.sleep(1)
 else:raise TimeoutError('server startup')
 model=api('/v1/models')['data'][0]['id']
 body={'model':model,'messages':[{'role':'user','content':'Write every integer from 1 to 2000, one integer per line. Do not summarize, use ellipses, or provide code. Begin immediately and continue until all 2000 are written.'}],'max_tokens':4096,'min_tokens':4096,'ignore_eos':True,'temperature':0,'seed':20260928,'chat_template_kwargs':{'enable_thinking':False}}
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  long=pool.submit(generation,body)
  for _ in range(60):
   metrics=control('metrics')
   if metrics.get('active_requests',0)>0:break
   if long.done():raise RuntimeError('generation ended before drain probe')
   time.sleep(.25)
  else:raise TimeoutError('no active request observed')
  report['before']=metrics;save();drain=pool.submit(refresh)
  time.sleep(.5)
  health_started=time.monotonic();report['during_control_status']=control('status');report['during_control_status_seconds']=time.monotonic()-health_started
  assert report['during_control_status'].get('state')=='paused'
  assert report['during_control_status_seconds']<2,'health polling blocked behind refresh'
  short=dict(body,max_tokens=1,min_tokens=0,ignore_eos=False,messages=[{'role':'user','content':'Hello'}])
  try:api('/v1/chat/completions',short);report['during_http_status']=200
  except urllib.error.HTTPError as e:report['during_http_status']=e.code
  report['generation']=long.result();report['refresh']=drain.result();save()
 assert report['during_http_status']==503,'admission opened during drain'
 assert report['refresh']['result'].get('state')=='active',report['refresh']
 assert report['refresh']['seconds']>60,'probe did not cross the old timeout boundary'
 report['after']=control('metrics');assert report['after']['state']=='active'
 report['post_refresh_response']=api('/v1/chat/completions',dict(body,max_tokens=8,min_tokens=0,ignore_eos=False,messages=[{'role':'user','content':'Say ready.'}]))
 report['status']='passed'
except BaseException as e:report.update(status='failed',error=repr(e));raise
finally:save()
print(json.dumps({'status':report['status'],'refresh_seconds':report.get('refresh',{}).get('seconds')}))
