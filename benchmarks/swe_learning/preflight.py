"""Real-model native publication replacement under an in-flight request."""
import concurrent.futures,json,pathlib,socket,subprocess,time,urllib.request,urllib.error
ROOT=pathlib.Path('/opt/aimee-memory-lab/swe-learning-20260926');URL='http://127.0.0.1:8170'
def ctl(body):
 with socket.socket(socket.AF_UNIX) as s:
  s.settimeout(180);s.connect(str(ROOT/'control.sock'));s.sendall(json.dumps(body).encode()+b'\n');return json.loads(s.makefile('rb').readline())
def publish(facts,retain=[]):return json.loads(subprocess.check_output(['python3',str(ROOT/'bridge.py')],input=json.dumps({'op':'publish','facts':facts,'retain':retain}).encode(),timeout=660))
def ask(pub,long=False):
 body={'model':model,'messages':[{'role':'user','content':'What is the synthetic beta verification key? State the number first.'+(' Then write 150 words about software testing.' if long else ' Return only the number.')}],'temperature':0,'max_tokens':256 if long else 32,'chat_template_kwargs':{'enable_thinking':False},'vllm_xargs':{'aimee_publication':pub}}
 started=time.monotonic()
 with urllib.request.urlopen(urllib.request.Request(URL+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=180) as r:d=json.load(r)
 return {'answer':d['choices'][0]['message']['content'],'seconds':time.monotonic()-started,'usage':d['usage']}
report={'status':'running','scope':'synthetic public canaries; dynamic native replacement, not changes to production Aimee records'}
try:
 for _ in range(420):
  try:
   with urllib.request.urlopen(URL+'/v1/models',timeout=2) as r:model=json.load(r)['data'][0]['id']
   break
  except (urllib.error.URLError,TimeoutError):time.sleep(1)
 else:raise TimeoutError('SWE server startup')
 old=publish(['The synthetic beta verification key is 38491.']);new=publish(['The synthetic beta verification key is 77283.'],[old['publication']]);report.update(old=old,new=new)
 with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
  future=pool.submit(ask,old['publication'],True)
  for _ in range(100):
   metrics=ctl({'op':'metrics'})
   if metrics.get('active_requests',0)>0:break
   time.sleep(.05)
  else:raise RuntimeError('no in-flight request observed')
  report['during']=metrics
  catalog=json.loads((ROOT/'catalog.json').read_text());catalog['publications'][old['publication']]=catalog['publications'][new['publication']]
  tmp=ROOT/'replacement.next';tmp.write_text(json.dumps(catalog));tmp.replace(ROOT/'catalog.json')
  report['refresh']=ctl({'op':'refresh'});assert report['refresh']['state']=='active'
  report['old_answer']=future.result();assert '38491' in report['old_answer']['answer']
 report['new_answer']=ask(old['publication']);assert '77283' in report['new_answer']['answer']
 withdrawn=ctl({'op':'withdraw'});report['withdrawn']=withdrawn
 try:ask(old['publication']);raise AssertionError('withdrawal bypassed')
 except urllib.error.HTTPError as e:assert e.code==503;report['withdrawal_http']=e.code
 report['stale_refresh']=ctl({'op':'refresh','generation':withdrawn['generation']-1});assert 'error' in report['stale_refresh']
 report['restored']=ctl({'op':'refresh','generation':withdrawn['generation']});assert report['restored']['state']=='active'
 report['restored_answer']=ask(old['publication']);assert '77283' in report['restored_answer']['answer']
 catalog['publications']={};tmp.write_text(json.dumps(catalog));tmp.replace(ROOT/'catalog.json');assert ctl({'op':'refresh'})['state']=='active'
 report['final_metrics']=ctl({'op':'metrics'});report['status']='passed'
except BaseException as e:report.update(status='failed',error=repr(e));raise
finally:(ROOT/'preflight.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
