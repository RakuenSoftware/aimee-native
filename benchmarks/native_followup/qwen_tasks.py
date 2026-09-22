"""Read the unchanged Gemma publication with the frozen Qwen Rust runtime."""
import hashlib,json,os,socketserver,subprocess,sys,threading,time,urllib.request
from http.server import BaseHTTPRequestHandler
from pathlib import Path
repo=Path(__file__).resolve().parents[2]
source=Path(sys.argv[1]);root=Path(sys.argv[2]);root.mkdir();os.chmod(root,0o755)
cases=json.loads((source/'cases.json').read_text())
def fingerprint():
    return {str(p.relative_to(source/'image')):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((source/'image').rglob('*')) if p.is_file()}
before=fingerprint();(root/'image-before.json').write_text(json.dumps(before,indent=2))
# Closed-world fixture has no upstream records. Never synthesizes a fact.
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path=='/identity':response={'authorization':'replication-empty-upstream'}
        elif self.path=='/search':response={'facts':[],'windows':[],'active_context_missing':False}
        elif self.path=='/resolve':response={'authorization':'replication-empty-upstream','refs':[]}
        else:self.send_error(404);return
        with (root/'gateway.jsonl').open('a') as f:f.write(json.dumps({'path':self.path,'request':request,'response':response})+'\n')
        data=json.dumps(response).encode();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def log_message(self,*args):pass
sock=root/'empty-upstream.sock';server=socketserver.UnixStreamServer(str(sock),Handler);os.chmod(sock,0o666)
threading.Thread(target=server.serve_forever,daemon=True).start()
traces=root/'traces';traces.mkdir();os.chown(traces,int(subprocess.check_output(['id','-u','memory-model'])),int(subprocess.check_output(['id','-g','memory-model'])))
command=['runuser','-u','memory-model','--','env','LD_LIBRARY_PATH=/opt/aimee-memory-lab/venv/lib/python3.13/site-packages/torch/lib','OMP_NUM_THREADS=8','MKL_NUM_THREADS=8',str(repo/'target/release/aimee-qwen'),'serve','--model','/opt/aimee-memory-lab/model','--placement',str(repo/'integrations/qwen_aimee/placement-dual7900xtx-int8.json'),'--int8','--memory-image',str(source/'image'),'--image-reader',str(repo/'.local/bin/aimee-memory-image'),'--read-gateway',str(sock),'--read-authority','test','--memory-limit','4','--trace-dir',str(traces),'--encoding-cache-mib','256','--enable-record-encoding']
(root/'command.json').write_text(json.dumps(command,indent=2))
log=(root/'server.log').open('x');proc=subprocess.Popen(command,stdout=log,stderr=log)

def score(answer,c):
    import decimal
    if c['scorer'] in ('number','integer'):
        try:
            a=decimal.Decimal(answer.strip());b=decimal.Decimal(c['expected']);return a.is_finite() and (a==b if c['scorer']=='integer' else abs(a-b)<=abs(b)*decimal.Decimal('0.00001'))
        except decimal.InvalidOperation:return False
    return answer.strip().rstrip('.').casefold()==c['expected'].strip().rstrip('.').casefold()
try:
    for attempt in range(600):
        if proc.poll() is not None:raise RuntimeError('Qwen startup failed')
        try:
            import socket
            connection=socket.create_connection(('127.0.0.1',18793),timeout=1);connection.close();break
        except OSError:time.sleep(1)
    else:raise TimeoutError('Qwen startup')
    for i,c in enumerate(cases):
        for enabled in ([False] if '--disabled-only' in sys.argv else [False,True]):
            payload=dict(model='qwen',messages=[dict(role='system',content='Answer using the available memory. Return only the requested value or values. If unknown, return unknown.'),dict(role='user',content=c['query'])],temperature=0,max_tokens=32,stream=False,aimee_memory=enabled,preload_memory=True,decode_recall=False,memory_encoding_granularity='record',reuse_encoding=False)
            start=time.perf_counter();request=urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=180) as response:result=json.load(response)
            answer=result['choices'][0]['message']['content'].strip()
            trace=json.loads((traces/(result['id']+'.json')).read_text())
            row=dict(case=c['id']+('-native' if enabled else '-disabled'),enabled=enabled,answer=answer,correct=score(answer,c),abstained=answer.rstrip('.').casefold()=='unknown',seconds=time.perf_counter()-start,response=result,request=payload,case_spec=c,prompt_token_ids=trace['prompt_token_ids'],memory_prompt_tokens=trace['memory_prompt_tokens'],native_reads=trace['native_reads'],memory_encoding_passes=trace['memory_encoding_passes'],main_cache_length=trace['main_cache_length'],recall_events=trace['recall_events'])
            with (root/'results.jsonl').open('a') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())
        if i%25==0:print(json.dumps(dict(completed=(i+1)*2,last=c['id'],answer=answer,correct=row['correct'])),flush=True)
finally:
    proc.terminate()
    try:proc.wait(timeout=30)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
    log.close();server.shutdown()
after=fingerprint();(root/'image-after.json').write_text(json.dumps(after,indent=2));assert before==after
(root/'DONE').write_text(str(time.time()))
