"""Read the unchanged Gemma publication with the frozen Qwen Rust runtime."""
import hashlib,json,os,socketserver,subprocess,sys,threading,time,urllib.request
from http.server import BaseHTTPRequestHandler
from pathlib import Path
repo=Path(__file__).resolve().parents[2]
source=Path(sys.argv[1]);root=Path(sys.argv[2]);root.mkdir();os.chmod(root,0o755)
if '--personal' in sys.argv:
    from republish_personal import prepare
    source=prepare(source,root.parent/'personal-source')
cases=json.loads((source/'cases.json').read_text())
if '--personal' in sys.argv:cases=[c for c in cases if c['source']=='personal']
if '--smoke' in sys.argv:cases=cases[:6]
import random
rng=random.Random(2026092412)
plan=[]
for c in cases:
    modes=['none','text','native'];rng.shuffle(modes);plan.append({'case':c,'modes':modes})
(root/'plan.json').write_text(json.dumps(plan,indent=2))
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

sys.path.insert(0,str(repo/'integrations/qwen_aimee'))
from local_image import AimeeImageClient
class Reader(AimeeImageClient):
    def __init__(self):
        self.process=subprocess.Popen([str(repo/'.local/bin/aimee-memory-image'),'serve-published','--root',str(source/'image')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)
        self.timeout=30;self.view=None;self.authorization_id=None
reader=Reader()
def ask(c,mode,phase='accuracy',repeat=0,reuse=False):
    probe=time.perf_counter();view=reader.begin_request()
    selected=reader.recall(c['query'],4,'test');assert selected['outcome']=='hit'
    facts=selected['response']['facts'];assert c['ref'] in [f.get('memory_ref') for f in facts]
    selection_seconds=time.perf_counter()-probe
    messages=[dict(role='system',content='Answer using the available memory. Return only the requested value or values. If unknown, return unknown.')]
    if mode=='text':messages.append(dict(role='system',content='Authoritative memory:\n'+'\n'.join(f['content'] for f in facts)))
    messages.append(dict(role='user',content=c['query']))
    payload=dict(model='qwen',messages=messages,temperature=0,max_tokens=32,stream=False,
        aimee_memory=mode=='native',preload_memory=True,decode_recall=False,
        memory_encoding_granularity='record',reuse_encoding=reuse)
    start=time.perf_counter()
    request=urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=180) as response:result=json.load(response)
    elapsed=time.perf_counter()-start
    trace=json.loads((traces/(result['id']+'.json')).read_text())
    answer=result['choices'][0]['message']['content'].strip()
    row=dict(case=c['id'],case_spec=c,phase=phase,repeat=repeat,mode=mode,answer=answer,
        correct=score(answer,c),selected_facts=facts,record_sha256=hashlib.sha256(json.dumps(facts,sort_keys=True).encode()).hexdigest(),
        source_view=view,selection_seconds=selection_seconds,model_request_seconds=elapsed,
        request_seconds=elapsed+(selection_seconds if mode=='text' else 0),
        ttft_seconds=None,ttft_unavailable_reason='archived Rust server is non-streaming and has no first-token timer',
        prompt_token_ids=trace['prompt_token_ids'],prompt_tokens=result['usage']['prompt_tokens'],
        completion_tokens=result['usage']['completion_tokens'],native_reads=trace['native_reads'],
        memory_encoding_passes=trace['memory_encoding_passes'],recall_events=trace['recall_events'],
        request=payload,response=result,trace=trace)
    with (root/'results.jsonl').open('a') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())
    if mode=='native':
        assert trace['native_reads']>0 and trace['memory_prompt_tokens']==0
        assert trace['recall_events'][0]['aimee_response']['facts']==facts
    else:assert trace['native_reads']==0 and trace['memory_encoding_passes']==0
    return row
try:
    for attempt in range(600):
        if proc.poll() is not None:raise RuntimeError('Qwen startup failed')
        try:
            import socket
            connection=socket.create_connection(('127.0.0.1',18793),timeout=1);connection.close();break
        except OSError:time.sleep(1)
    else:raise TimeoutError('Qwen startup')
    for i,item in enumerate(plan):
        rows={mode:ask(item['case'],mode) for mode in item['modes']}
        assert rows['native']['prompt_token_ids']==rows['none']['prompt_token_ids']
        assert len({r['record_sha256'] for r in rows.values()})==1
        assert rows['text']['prompt_tokens']>rows['none']['prompt_tokens']
        if i%10==0:print(json.dumps(dict(completed_cases=i+1,total=len(plan),scores={m:r['correct'] for m,r in rows.items()})),flush=True)
    for c in cases[:(2 if '--smoke' in sys.argv else 32)]:
        for mode in ['text','native']:ask(c,mode,'warmup',reuse=True)
        for repeat in range(1,6):
            modes=['text','native'];rng.shuffle(modes)
            for mode in modes:
                row=ask(c,mode,'reuse',repeat,reuse=True)
                if mode=='native':assert row['memory_encoding_passes']==0
    after=fingerprint();(root/'image-after.json').write_text(json.dumps(after,indent=2));assert before==after
    (root/'DONE').write_text(str(time.time()))
finally:
    reader.close();proc.terminate()
    try:proc.wait(timeout=30)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
    log.close();server.shutdown()
