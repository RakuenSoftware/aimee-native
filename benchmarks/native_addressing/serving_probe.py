"""Isolated current-source serving validation with existing public synthetic banks.
Runs two weight profiles, matched text controls, growing conversation, and checks
actual worker telemetry. Reuses prepared banks; does not certify fresh authority.
"""
import argparse,hashlib,json,os,signal,socket,subprocess,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for k in ('output','python','plugin','library','model','catalog','weights'):p.add_argument('--'+k,required=True)
p.add_argument('--wait-for');p.add_argument('--port',type=int,default=18945);a=p.parse_args()
root=Path(a.output);root.mkdir(mode=0o700)
if a.wait_for:
 while not Path(a.wait_for).exists():time.sleep(2)
catalog=json.loads(Path(a.catalog).read_text());reports={}
for profile in ('bf16','q8'):
 work=root/profile;work.mkdir();control=work/'control.sock'
 config={'catalog':a.catalog,'recipient':catalog['recipient'],'model':a.model,'library':a.library,'host_memory_budget':512*1024**2,'device_memory_budget':256*1024**2,'disk_backed':True,'native_stage_telemetry':True,'control_socket':str(control),'serve':{'tensor_parallel_size':2,'port':a.port,'gpu_memory_utilization':.70,'max_model_len':2048,'max_num_seqs':4,'max_num_batched_tokens':256}}
 if profile=='q8':config['gguf_weights']=a.weights
 (work/'config.json').write_text(json.dumps(config,indent=2)+'\n')
 env={**os.environ,'PYTHONPATH':a.plugin,'LD_LIBRARY_PATH':'/opt/aimee-memory-lab/vllm-rocm-libs:/opt/aimee-memory-lab/vllm-os-libs/usr/lib/x86_64-linux-gnu:/opt/aimee-memory-lab/vllm-env/lib/python3.12/site-packages/torch/lib','OMP_NUM_THREADS':'2'}
 command=[a.python,'-m','aimee_vllm.cli','--config',str(work/'config.json')]
 report={'profile':profile,'argv':command,'status':'starting','library_sha256':hashlib.sha256(Path(a.library).read_bytes()).hexdigest(),'scope':'current plugin and portable library; existing synthetic prepared states; no fresh production authorization or encoder claim'}
 def save():(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 save()
 with open(work/'server.log','xb') as log:
  proc=subprocess.Popen(command,stdout=log,stderr=log,env=env,start_new_session=True)
  try:
   deadline=time.monotonic()+900
   while True:
    if proc.poll() is not None:raise RuntimeError('serving exited')
    try:
     with urllib.request.urlopen(f'http://127.0.0.1:{a.port}/health',timeout=2):break
    except Exception:
     if time.monotonic()>deadline:raise
     time.sleep(1)
   subprocess.run(['python3',str(Path(a.plugin)/'serving_matrix.py'),'--endpoint',f'http://127.0.0.1:{a.port}','--output',str(work/'matrix.json'),'--label','current-source-'+profile],check=True)
   matrix=json.loads((work/'matrix.json').read_text());report['summary']=matrix['summary'];report['correct']=sum(r['correct'] for r in matrix['rows']);report['n']=len(matrix['rows'])
   with socket.socket(socket.AF_UNIX) as sock:
    sock.settimeout(60);sock.connect(str(control));sock.sendall(b'{"op":"metrics"}\n');report['metrics']=json.loads(sock.makefile('rb').readline())
   report['status']='passed' if report['correct']==report['n'] else 'quality_gate_failed'
   if len(report['metrics'].get('workers',[]))!=2:raise RuntimeError('worker telemetry absent')
   if not all(w.get('host_stages',{}).get('enabled') for w in report['metrics']['workers']):raise RuntimeError('worker telemetry disabled')
  except BaseException as e:report.update(status='failed',error=str(e));save();raise
  finally:
   save()
   if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(timeout=45)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
 reports[profile]=report
(root/'results.json').write_text(json.dumps(reports,indent=2)+'\n')
print(json.dumps({k:{'status':v['status'],'correct':v['correct'],'n':v['n']} for k,v in reports.items()}))
