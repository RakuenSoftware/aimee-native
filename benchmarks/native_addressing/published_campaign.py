"""Full-model probe of the actual compiled published reader, using public data.
The empty fallback fixture returns no records and knows no task answers. It is
not evidence of production remote authorization. All bundle selection uses Go.
"""
import argparse,hashlib,json,os,signal,socket,socketserver,subprocess,threading,time
from pathlib import Path
from campaign import TASKS,SYSTEM,request,new_json
class EmptyFallback(socketserver.StreamRequestHandler):
    def handle(self):
        line=self.rfile.readline().decode();path=line.split()[1];length=0
        while True:
            header=self.rfile.readline()
            if header in (b'\r\n',b'\n',b''):break
            if header.lower().startswith(b'content-length:'):length=int(header.split(b':')[1])
        self.rfile.read(length)
        if path=='/identity':body={'authorization':'public-empty-fixture'}
        elif path=='/search':body={'status':'ok','facts':[],'windows':[],'active_context_missing':False}
        elif path=='/resolve':body={'authorization':'public-empty-fixture','refs':[]}
        else:raise ValueError('unexpected fixture operation')
        data=json.dumps(body).encode();self.wfile.write(f'HTTP/1.1 200 OK\r\nContent-Length: {len(data)}\r\nConnection: close\r\n\r\n'.encode()+data)
def main(a):
    root=Path(a.output);root.mkdir(mode=0o700)
    tasks=list(TASKS)
    for relay,station,code in [('neris','orinth','7391'),('tavren','velmar','4826'),('merisol','selvek','9153')]:
        tasks.append({'id':relay+'-paraphrase','query':f'For {relay.title()}, give the entry number at its destination.','answer':code,'expected':[relay,station]})
        tasks.append({'id':relay+'-alias','query':f'Which station code is reachable from {relay.title()} outpost?','answer':code,'expected':[relay,station]})
    if a.tasks:tasks=json.loads(Path(a.tasks).read_text())['tasks']
    new_json(root/'protocol.json',{'tasks':tasks,'schedules':a.schedules,'turns':a.turns,'profile':('complete-hybrid-system-message-v1' if a.encoding.startswith('system-message') else 'complete-hybrid-content-v1') if a.hybrid else 'attention-only-record-v1','archive':a.archive,'gate':'all 16 exact outcomes and required canonical records on every schedule; no stale revisions; native memory tokens excluded from conversation','model_config_sha256':hashlib.sha256((Path(a.model)/'config.json').read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(Path(a.binary).read_bytes()).hexdigest(),'reader_sha256':hashlib.sha256(Path(a.reader).read_bytes()).hexdigest(),'timing_scope':'descriptive completed HTTP wall; startup and empty fallback separate from warm routing; no inference of consumption time'})
    gateway=str(root/'empty.sock');server=socketserver.UnixStreamServer(gateway,EmptyFallback);threading.Thread(target=server.serve_forever,daemon=True).start()
    rows=[]
    try:
      for schedule in a.schedules:
        traces=root/schedule;traces.mkdir()
        cmd=[a.binary,'serve','--model',a.model,'--placement',a.placement,'--int8','--image-reader',a.reader,'--memory-image',a.archive,'--read-gateway',gateway,'--read-authority','public-research','--trace-dir',str(traces),'--port',str(a.port),'--encoding-cache-mib','256','--native-schedule',schedule,'--native-refresh-interval','4','--max-active-records','6','--enable-record-encoding','--enable-memory-diagnostics','--native-candidate-routing']
        if a.hybrid:cmd+=['--enable-hybrid-native']
        if a.prepared:cmd+=['--prepared-memory',a.prepared,'--prepared-model-revision',a.revision]
        if schedule=='bounded-refresh':cmd+=['--native-max-reads','8']
        new_json(root/(schedule+'-invocation.json'),{'argv':cmd})
        with open(root/(schedule+'-server.log'),'xb') as log:
          proc=subprocess.Popen(cmd,stdout=log,stderr=log,start_new_session=True)
          try:
            deadline=time.monotonic()+900
            while True:
              if proc.poll() is not None:raise RuntimeError('model exited')
              try:request(a.port);break
              except Exception:
                if time.monotonic()>deadline:raise
                time.sleep(1)
            for turns in a.turns:
              for task in tasks:
                messages=[{'role':'system','content':SYSTEM}]
                for _ in range(turns):messages.extend([{'role':'user','content':'We are planning a meeting.'},{'role':'assistant','content':'Understood.'}])
                messages.append({'role':'user','content':task['query']})
                response=request(a.port,{'messages':messages,'max_tokens':32,'temperature':0,'memory_encoding_granularity':'bank' if a.hybrid else 'record','native_recurrent_state':a.hybrid,'memory_encoding':a.encoding})
                tracepath=traces/(response['id']+'.json');trace=json.loads(tracepath.read_text());answer=response['choices'][0]['message']['content'].strip().rstrip('.')
                actual={(f['memory_ref']['namespace'],f['memory_ref']['id'],f['memory_ref']['revision']) for e in trace['recall_events'] for f in e.get('aimee_response',{}).get('facts',[])}
                expected={('public-research-fixture',id,'1') for id in task['expected']}
                selection=(expected<=actual) if expected else not actual
                row={'schedule':schedule,'turns':turns,'task':task['id'],'answer':answer,'correct':answer.lower()==task['answer'],'selection_correct':selection,'trace':str(tracepath.relative_to(root)),'trace_sha256':hashlib.sha256(tracepath.read_bytes()).hexdigest(),'elapsed_ms':trace['elapsed_ms'],'memory_prompt_tokens':trace.get('memory_prompt_tokens'),'metrics':trace['native_memory_metrics']}
                rows.append(row);print(json.dumps(row),flush=True)
          finally:
            if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=30)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        new_json(root/(schedule+'-results.json'),[r for r in rows if r['schedule']==schedule])
      new_json(root/'results.json',{'rows':rows,'correct':sum(r['correct'] for r in rows),'selection_correct':sum(r['selection_correct'] for r in rows),'n':len(rows)})
    finally:server.shutdown();server.server_close()
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('output','archive','binary','model','placement','reader'):p.add_argument('--'+key,required=True)
 p.add_argument('--port',type=int,default=18944);p.add_argument('--schedules',nargs='+',default=['every-step','preload-only','bounded-refresh'])
 p.add_argument('--encoding',choices=['content','system-message','system-message-keyed'],default='content');p.add_argument('--hybrid',action='store_true');p.add_argument('--tasks');p.add_argument('--turns',type=int,nargs='+',default=[0,16]);p.add_argument('--prepared');p.add_argument('--revision')
 main(p.parse_args())
