"""Repeated real-source publication latency; no model inference or fake mutations.
Run only in a prepare_live.py-created disposable research directory on .253.
The final update restores the original approved synthetic fact.
"""
import argparse,json,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--rounds',type=int,default=6);a=p.parse_args();r=a.root
meta=json.loads((r/'private/records.json').read_text());assert meta['project']=='aimee-layered-kb-20260920';assert a.rounds>=2
out=r/'publication-timings.jsonl';assert not out.exists()
program='''import http.client,socket,json,sys
class U(http.client.HTTPConnection):
 def connect(self):self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.connect(self.host)
x=json.load(sys.stdin);c=U(x['socket']);c.request('POST','/v1/memory/store',json.dumps(x['body']),{'Content-Type':'application/json'});reply=c.getresponse();v=json.loads(reply.read());assert reply.status==200 and v['status']=='ok';print(json.dumps(v))
'''
def head():
 try:return json.loads((r/'image/CURRENT').read_text())['view']
 except FileNotFoundError:return None
for i in range(a.rounds):
 old=head();assert old
 body={k:meta['drink'][k] for k in ['kind','tier','key','confidence','content']}
 if i!=a.rounds-1:body['content']=f'The preferred drink of stream-unit-d47 is experimental-tea-{i}.'
 started=time.perf_counter()
 reply=json.loads(subprocess.check_output(['pct','exec','103','--','python3','-c',program],input=json.dumps(dict(socket=meta['bus'].replace('server-module-bus.sock','aimee-http.sock'),body=body)),text=True));assert reply['id']==meta['drink']['id']
 mutation_seconds=time.perf_counter()-started
 while time.perf_counter()-started<300:
  view=head()
  if view and view!=old:break
  time.sleep(.01)
 else:raise RuntimeError('publication failed')
 elapsed=time.perf_counter()-started
 events=[]
 for _ in range(100):
  events=[json.loads(x) for x in (r/'consumer.log').read_text().splitlines() if x.startswith('{')]
  if any(e.get('view')==view for e in events):break
  time.sleep(.01)
 row=dict(round=i+1,publication_seconds=elapsed,mutation_seconds=mutation_seconds,view=view,delivery=next((e for e in reversed(events) if e.get('view')==view),None))
 with out.open('a') as f:f.write(json.dumps(row)+'\n')
 print(json.dumps(row),flush=True)
 time.sleep(.2)
