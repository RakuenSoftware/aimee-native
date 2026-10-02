"""Run the matched matrix against a freshly started private BF16 fixture server."""
import argparse,json,pathlib,subprocess,time,urllib.request
p=argparse.ArgumentParser();p.add_argument('--root',default='/opt/aimee-memory-lab');p.add_argument('--output',required=True);a=p.parse_args()
root=pathlib.Path(a.root);fixture=root/'vllm-native-fixture-r1';config=json.loads((fixture/'disk-config.json').read_text());config['serve']={'tensor_parallel_size':2,'port':8151};path=fixture/'bf16-matrix-config.json';path.write_text(json.dumps(config));log=open(a.output+'.server.log','w')
child=subprocess.Popen([str(root/'vllm-env/bin/aimee-vllm'),'--config',str(path)],stdout=log,stderr=subprocess.STDOUT)
try:
 for _ in range(300):
  if child.poll() is not None:raise RuntimeError('matrix runtime exited')
  try:
   with urllib.request.urlopen('http://127.0.0.1:8151/health',timeout=2):break
  except Exception:time.sleep(1)
 else:raise TimeoutError('matrix server startup')
 subprocess.run([str(root/'vllm-env/bin/python'),str(pathlib.Path(__file__).with_name('serving_matrix.py')),'--endpoint','http://127.0.0.1:8151','--label','private-gemma-bf16','--output',a.output],check=True)
finally:
 child.terminate()
 try:child.wait(timeout=45)
 except subprocess.TimeoutExpired:child.kill();child.wait()
 log.close()
