"""Live Aimee mutations -> streamed local KB -> frozen Rust/Qwen native answers.
Run on .253 against the explicitly prepared disposable project only.
"""
import argparse,json,os,subprocess,time,urllib.request,urllib.error
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',default='live-results.jsonl');p.add_argument('--start-at',choices=['begin','supersede','finish-same-id'],default='begin');a=p.parse_args();r=a.root
meta=json.loads((r/'private/records.json').read_text());assert meta['project']=='aimee-layered-kb-20260920'
out=r/a.output;assert not out.exists(),'Preserve previous results'
AIMEE="""import http.client,socket,json,sys
class U(http.client.HTTPConnection):
 def connect(self):self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.connect(self.host)
x=json.load(sys.stdin);c=U(x['socket'],timeout=60);c.request('POST',x['route'],json.dumps(x['body']),{'Content-Type':'application/json'});reply=c.getresponse();v=json.loads(reply.read());assert reply.status==200 and v['status']=='ok',v;print(json.dumps(v))
"""
def write(row):
 with out.open('a') as f:f.write(json.dumps(row)+'\n')
 print(json.dumps({k:v for k,v in row.items() if k not in ['response','trace','query','prompt_token_ids']}),flush=True)
def head():
 try:return json.loads((r/'image/CURRENT').read_text())['view']
 except FileNotFoundError:return None
def mutate(route,body):
 return json.loads(subprocess.check_output(['pct','exec','103','--','python3','-c',AIMEE],input=json.dumps(dict(socket=meta['bus'].replace('server-module-bus.sock','aimee-http.sock'),route='/v1/memory/'+route,body=body)),text=True))
def advance(old,started,case):
 for _ in range(1200):
  view=head()
  if view and view!=old:
   for _ in range(30):
    logs=[json.loads(x) for x in (r/'consumer.log').read_text().splitlines() if x.startswith('{')]
    events=[x for x in logs if x.get('view')==view]
    if events:break
    time.sleep(.1)
   row=dict(case=case,publication_seconds=time.perf_counter()-started,previous=old,view=view,delivery=events[-1] if events else None)
   write(row);return view
  time.sleep(.25)
 raise RuntimeError('publication did not advance')
def ask(case,query,expected,**flags):
 payload=dict(messages=[dict(role='system',content='Answer using the available memory. Return only the requested value or values. If unknown, return unknown.'),dict(role='user',content=query)],max_tokens=40,temperature=0,memory_encoding_granularity='record',**flags)
 started=time.perf_counter()
 try:
  with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'}),timeout=300) as response:reply=json.load(response)
 except urllib.error.HTTPError as e:
  write(dict(case=case,query=query,expected=expected,error=e.read().decode(),http_status=e.code,seconds=time.perf_counter()-started));raise
 t=json.loads((r/'traces'/(reply['id']+'.json')).read_text());answer=reply['choices'][0]['message']['content']
 events=t['recall_events'];banks=[e['bank_memory_ids'] for e in events if 'bank_memory_ids' in e]
 row=dict(case=case,query=query,expected=expected,answer=answer,pass_=answer.replace(' ','')==expected.replace(' ',''),seconds=time.perf_counter()-started,encodings=t['memory_encoding_passes'],cache_transition=t['cache_transition'],cache_hits=sum(e.get('record_cache_hits',0) for e in events),memory_prompt_tokens=t['memory_prompt_tokens'],view=t['publication'],bank=banks[-1] if banks else [],response=reply,prompt_token_ids=t['prompt_token_ids'])
 assert row['memory_prompt_tokens']==0;write(row);return row
Q='Give the TCP port for IANA service xic, then the preferred drink of stream-unit-d47, then the home city of stream-unit-c92. Separate the three values with semicolons.'
def scan(case,forbidden):
 matches=[]
 for file in (r/'image').rglob('*'):
  if file.is_file():
   with file.open('rb') as f:
    tail=b''
    while data:=f.read(4<<20):
     if any(x in tail+data for x in forbidden):matches.append(str(file.relative_to(r/'image')))
     tail=data[-4096:]
 write(dict(case=case,pass_=not matches,files_with_forbidden_content=matches));assert not matches
if a.start_at=='begin':
 # Repair the disposable fixture sequence after its historical explicit IDs.
 subprocess.run(['pct','exec','103','--','docker','exec','-i',meta['project']+'-aimee-store-db-1','sh','-c','PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U postgres -d aimee_store -v ON_ERROR_STOP=1'],input="SELECT setval(pg_get_serial_sequence('user_memories','id'), (SELECT max(id) FROM user_memories));",text=True,stdout=subprocess.DEVNULL,check=True)
 scan('unauthorized-canary-excluded',[meta['canary']['content'].encode()])
 ask('baseline-cold',Q,'6115;oolong;Lima')
 assert ask('baseline-warm',Q,'6115;oolong;Lima')['encodings']==0
 old=head();start=time.perf_counter();body={k:meta['drink'][k] for k in ['kind','tier','key','confidence']};body['content']='The preferred drink of stream-unit-d47 is jasmine.'
 reply=mutate('store',body);assert reply['id']==meta['drink']['id'];advance(old,start,'update-publication')
 answer=ask('after-update',Q,'6115;jasmine;Lima');assert answer['encodings']==1 and answer['cache_transition']==dict(retained=2,invalidated=1),answer
 assert ask('update-warm',Q,'6115;jasmine;Lima')['encodings']==0
 scan('updated-content-excluded',[meta['canary']['content'].encode(),meta['drink']['content'].encode()])
 old=head();start=time.perf_counter();mutate('delete',dict(id=meta['city']['id']));advance(old,start,'delete-publication')
 answer=ask('after-delete',Q,'6115;jasmine;unknown');assert answer['encodings']==0 and answer['cache_transition']==dict(retained=2,invalidated=1),answer
 scan('deleted-content-excluded',[meta['canary']['content'].encode(),meta['city']['content'].encode()])
if a.start_at=='finish-same-id':
 reply=[json.loads(x)['response'] for x in (r/'live-results-r3.jsonl').read_text().splitlines() if json.loads(x)['case']=='aimee-supersede'][-1]
 old=[json.loads(x)['view'] for x in (r/'live-results-r2.jsonl').read_text().splitlines() if json.loads(x)['case']=='after-delete'][-1]
 write(dict(case='resume-supersession',reason='Aimee server supersede preserved canonical ID; test now follows observed source identity'))
 start=time.perf_counter();advance(old,start,'supersession-observed-after-resume')
else:
 old=head();start=time.perf_counter();reply=mutate('supersede',dict(old_id=meta['drink']['id'],new_content='The preferred drink of stream-unit-d47 is mint.',confidence=1));write(dict(case='aimee-supersede',response=reply))
 advance(old,start,'supersession-publication')
new_id=reply.get('new_id',reply.get('id'));assert isinstance(new_id,int),reply
replacement='mint'
if new_id==meta['drink']['id']:
 # The current server-placement API updates this canonical ID. Honor Aimee's
 # identity decision; do not fabricate a new identity in the adapter.
 answer=ask('after-supersession',Q,'6115;mint;unknown');assert answer['encodings']==1 and answer['cache_transition']==dict(retained=1,invalidated=1),answer
 scan('superseded-content-excluded',[b'The preferred drink of stream-unit-d47 is jasmine.'])
 replacement='chamomile';before=head()
 created=mutate('store',dict(kind='fact',tier='L3',key='stream replacement 20260921',content='The preferred drink of stream-unit-d47 is chamomile.',confidence=1))
 new_id=created['id'];assert new_id!=meta['drink']['id'];time.sleep(3)
 write(dict(case='new-unapproved-record-does-not-publish',pass_=head()==before,new_id=new_id));assert head()==before
 scan('unapproved-replacement-excluded',[b'The preferred drink of stream-unit-d47 is chamomile.'])
else:
 scan('unapproved-replacement-excluded',[b'The preferred drink of stream-unit-d47 is mint.'])
policy=json.loads((r/'private/release.json').read_text());policy['records'][0]['id']=str(new_id)
def publish_policy(p):
 tmp=r/'private/release.next';tmp.write_text(json.dumps(p,indent=2));tmp.chmod(0o600);tmp.replace(r/'private/release.json')
old=head();start=time.perf_counter();publish_policy(policy);advance(old,start,'replacement-approved')
answer=ask('after-replacement-approval',Q,f'6115;{replacement};unknown');assert answer['encodings']==1 and answer['cache_transition']==dict(retained=1,invalidated=1),answer
old=head();start=time.perf_counter();policy['records']=[];publish_policy(policy);advance(old,start,'authorization-narrowed')
answer=ask('unrelated-after-narrowing','Give the TCP port for IANA service xic. Return the integer only.','6115');assert answer['encodings']==0 and answer['cache_transition']==dict(retained=1,invalidated=1),answer
scan('narrowed-content-excluded',[f'The preferred drink of stream-unit-d47 is {replacement}.'.encode(),meta['canary']['content'].encode()])
print('live mutation pipeline complete',flush=True)
