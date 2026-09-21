"""Post-mutation safety/reconnect checks for the disposable live publication.
Leaves release inactive and model-facing bytes withdrawn on completion.
"""
import argparse,concurrent.futures,json,os,subprocess,time,urllib.request,urllib.error
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',default='safety-results.jsonl');p.add_argument('--skip-reconnect',action='store_true');a=p.parse_args();r=a.root
assert json.loads((r/'setup.json').read_text())['project']=='aimee-layered-kb-20260920'
out=r/a.output;assert not out.exists()
def log(**v):
 with out.open('a') as f:f.write(json.dumps(v)+'\n')
 print(json.dumps(v),flush=True)
def head():
 try:return json.loads((r/'image/CURRENT').read_text())['view']
 except FileNotFoundError:return None
def wait_for(f,timeout=240):
 t=time.perf_counter()
 while not f():
  if time.perf_counter()-t>timeout:raise RuntimeError('timed out')
  time.sleep(.05)
 return time.perf_counter()-t
policy=json.loads((r/'private/release.json').read_text())
def publish(v):
 tmp=r/'private/release.safety-next';tmp.write_text(json.dumps(v));tmp.chmod(0o600);tmp.replace(r/'private/release.json')
# Model identity cannot inspect the publisher's private source or mutate delivery.
for label,path,permission in [('private-policy',r/'private/release.json','r'),('image-write',r/'image/CURRENT','w')]:
 code='import os,sys;os.setgid(989);os.setuid(997);sys.exit(1 if os.access(sys.argv[1],os.R_OK if sys.argv[2]=="r" else os.W_OK) else 0)'
 result=subprocess.run(['python3','-c',code,str(path),permission]);log(case=label,pass_=result.returncode==0);assert result.returncode==0
if not a.skip_reconnect:
 old=head();start=time.perf_counter();subprocess.run(['systemctl','stop','aimee-stream-consumer'],check=True)
 assert head() is None;log(case='disconnect-withdraws',pass_=True,seconds=time.perf_counter()-start)
 start=time.perf_counter();subprocess.run(json.loads((r/'consumer-command.json').read_text()),check=True);wait_for(lambda:head()==old)
 logs=[json.loads(x) for x in (r/'consumer.log').read_text().splitlines() if x.startswith('{')];event=[x for x in logs if x.get('view')==old][-1]
 log(case='reconnect-restores-same-generation',pass_=True,seconds=time.perf_counter()-start,delivery=event)
def ask():
 payload=dict(messages=[dict(role='user',content='Give the TCP port for IANA service xic, then explain TCP in at least 500 words.')],max_tokens=512,temperature=0,memory_encoding_granularity='record')
 try:
  with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'}),timeout=180) as response:return response.status,json.load(response)
 except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
 before_traces=set((r/'traces').glob('*-failed.json'))
 future=pool.submit(ask);time.sleep(30)
 active=not future.done();start=time.perf_counter();policy['active']=False;publish(policy);wait_for(lambda:head() is None,30)
 withdrawn=time.perf_counter()-start;status,response=future.result()
 failed=list(set((r/'traces').glob('*-failed.json'))-before_traces)
 steps=[event.get('step',0) for path in failed for event in json.loads(path.read_text()).get('recall_events',[]) or []]
 maximum_step=max(steps,default=0)
 log(case='inflight-withdrawal',request_active_at_withdrawal=active,http_status=status,response=response,withdrawal_seconds=withdrawn,maximum_native_step=maximum_step,failed_traces=[p.name for p in failed],pass_=active and status!=200 and maximum_step>0)
 assert active and status!=200 and maximum_step>0
files=[str(p.relative_to(r/'image')) for p in (r/'image/snapshots').rglob('*') if p.is_file()]
log(case='withdrawn-image-no-record-bytes',pass_=not files,file_count=len(files));assert not files
