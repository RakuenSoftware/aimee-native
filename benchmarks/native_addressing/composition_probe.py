"""Development diagnosis: exact source, independent/joint native states and text.
Old failures are development cases. Any candidate fix needs a fresh frozen holdout.
"""
import argparse,json,os,signal,subprocess,time
from pathlib import Path
from campaign import SYSTEM,request,new_json
from published_campaign import EmptyFallback
import socketserver,threading

def main(a):
 root=Path(a.output);root.mkdir(mode=0o700);traces=root/'traces';traces.mkdir()
 tasks=json.loads(Path(a.protocol).read_text())['tasks']
 variants=[('record-content','record','content'),('bank-content','bank','content'),('bank-keyed','bank','keyed'),('bank-json','bank','json'),('text-control',None,None),('disabled',None,None),('record-chat','record','chat-content'),('bank-chat','bank','chat-content'),('bank-chat-keyed','bank','chat-keyed'),('hybrid-content','bank','content'),('hybrid-chat','bank','chat-content'),('hybrid-chat-keyed','bank','chat-keyed'),('hybrid-system-message','bank','system-message'),('hybrid-system-message-keyed','bank','system-message-keyed')]
 if a.variants:variants=[v for v in variants if v[0] in a.variants]
 if a.wait_for:
  while not Path(a.wait_for).exists():time.sleep(2)
 new_json(root/'protocol.json',{'scope':__doc__,'tasks':tasks,'variants':variants,'system':SYSTEM,'gate':'diagnosis only; no promotion from development cases'})
 server=socketserver.UnixStreamServer(str(root/'empty.sock'),EmptyFallback);threading.Thread(target=server.serve_forever,daemon=True).start()
 cmd=[a.binary,'serve','--model',a.model,'--placement',a.placement,'--int8','--image-reader',a.reader,'--memory-image',a.archive,'--read-gateway',str(root/'empty.sock'),'--read-authority','public-research','--trace-dir',str(traces),'--port',str(a.port),'--encoding-cache-mib','256','--native-schedule','preload-only','--max-active-records','6','--enable-record-encoding','--enable-memory-diagnostics','--enable-hybrid-native','--native-candidate-routing']
 source=subprocess.Popen([a.reader,'serve-published','--root',a.archive],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 def read(query):
  source.stdin.write(json.dumps({'op':'recall','query':query,'limit':6,'authority':'public-research'})+'\n');source.stdin.flush();return json.loads(source.stdout.readline())
 source.stdin.write('{"op":"pin"}\n');source.stdin.flush();assert 'view' in json.loads(source.stdout.readline())
 rows=[]
 with open(root/'server.log','xb') as log:
  proc=subprocess.Popen(cmd,stdout=log,stderr=log,start_new_session=True)
  try:
   deadline=time.monotonic()+900
   while True:
    if proc.poll() is not None:raise RuntimeError('model exited')
    try:request(a.port);break
    except Exception:
     if time.monotonic()>deadline:raise
     time.sleep(1)
   for name,granularity,encoding in variants:
    for task in tasks:
     messages=[{'role':'system','content':SYSTEM}]
     if name=='text-control':
      recalled=read(task['query']);facts=recalled.get('response',{}).get('facts',[])
      if facts:messages[0]['content']+='\n\nAuthoritative memory:\n'+'\n'.join(f['content'] for f in facts)
     messages.append({'role':'user','content':task['query']})
     body={'messages':messages,'max_tokens':32,'temperature':0,'aimee_memory':granularity is not None,'native_recurrent_state':name.startswith('hybrid-')}
     if granularity:body.update(memory_encoding_granularity=granularity,memory_encoding=encoding)
     if name.startswith('hybrid-'):body['native_recurrent_state']=True
     response=request(a.port,body);answer=response['choices'][0]['message']['content'].strip().rstrip('.')
     row={'variant':name,'task':task['id'],'correct':answer.lower()==task['answer'],'answer':answer,'trace':response['id']}
     rows.append(row);print(json.dumps(row),flush=True)
   new_json(root/'results.json',rows)
  finally:
   if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(timeout=30)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
   source.stdin.close();source.wait(timeout=10);server.shutdown();server.server_close()
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for k in ('output','protocol','binary','model','placement','reader','archive'):p.add_argument('--'+k,required=True)
 p.add_argument('--variants',nargs='+');p.add_argument('--wait-for');p.add_argument('--port',type=int,default=18946);main(p.parse_args())
