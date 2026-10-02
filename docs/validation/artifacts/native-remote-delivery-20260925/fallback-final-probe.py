import pathlib,subprocess,json,tempfile,threading,socketserver,http.server,os,time
lab=pathlib.Path('/opt/aimee-memory-lab');build=lab/'vllm-native-build';base=json.loads((lab/'preparation-check-r1/config.json').read_text());out=lab/'native-fallback-report-final.json'
reader=subprocess.Popen([base['image_reader'],'serve-published','--root',base['memory_image']],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
def call(q):reader.stdin.write(json.dumps(q)+'\n');reader.stdin.flush();return json.loads(reader.stdout.readline())
pin=call({'op':'pin'});response=call({'op':'recall','query':'alpha vault alpha project alpha drink','limit':8,'authority':base['authority']})['response'];approved=call({'op':'resolve_local_response','response':response});reader.terminate();reader.wait()
report={'authority':'protocol fixture for existing authenticated fallback contract; actual scoped local reader and Rust preparer; not production remote authorization','checks':{}}
with tempfile.TemporaryDirectory() as directory:
 root=pathlib.Path(directory);socket=root/'gateway.sock';state={'mode':'pass','searches':0}
 class Handler(http.server.BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_POST(self):
   q=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
   if self.path=='/identity':result={'authorization':'remote-fixture'}
   else:
    assert q.get('authorization')=='remote-fixture'
    if self.path=='/search':
     state['searches']+=1;result=json.loads(json.dumps(response));result['windows']=[];result['active_context_missing']=False
     if state['mode']=='context':result['active_context_missing']=True
     if state['mode']=='windows' or (state['mode']=='late_windows' and state['searches']>1):result['windows']=[{'content':'required additional context'}]
     if state['mode']=='changed' and state['searches']>1:result['facts'][0]['content']='changed during preparation'
    elif self.path=='/resolve':
     result={'authorization':'remote-fixture','view':pin['view'],'refs':approved['refs']}
     if state['mode']=='partial':result['refs']=result['refs'][:1]
     if state['mode']=='denied':result['authorization']='wrong-binding'
    else:raise AssertionError(self.path)
   b=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 server=socketserver.UnixStreamServer(str(socket),Handler);os.chmod(socket,0o600);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  for mode in ['pass','partial','denied','changed','context','windows','late_windows','unconfigured']:
   c=dict(base);c['gateway']=str(socket);c['query']='deliberate remote-only query unmatched by local cues';c['cache_root']=str(root/'must-not-exist');c['compiler']=['/compiler/must/not/run']
   if mode=='unconfigured':del c['gateway']
   state.update(mode=mode,searches=0);config=root/'config.json';config.write_text(json.dumps(c))
   r=subprocess.run([str(build/'target/release/native-prepare'),str(config),'--check'],capture_output=True,text=True)
   if mode=='pass':
    assert r.returncode==0,r.stderr;result=json.loads(r.stdout);assert result['records']==approved['refs'] and len(result['records'])==3;report['checks'][mode]={'passed':True,'records':result['records'],'remote_searches':state['searches']}
   else:assert r.returncode!=0,mode;report['checks'][mode]={'passed':True,'rejected':True}
   assert not (root/'must-not-exist').exists()
  report['status']='passed'
 finally:server.shutdown();server.server_close();thread.join();out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
