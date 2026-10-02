"""Run actual scoped reader and private CPU compiler, then verify cache reuse."""
import argparse,json,os,pathlib,subprocess,time
p=argparse.ArgumentParser();p.add_argument('--root',default='/opt/aimee-memory-lab');p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--encoding-revision',required=True);p.add_argument('--publisher-library',required=True);a=p.parse_args()
root=pathlib.Path(a.root);build=root/'vllm-native-build';source=json.loads(pathlib.Path(a.source).read_text())
c={'image_reader':str(root/'aimee-memory-image-release'),'memory_image':source['root'],'query':'alpha vault alpha project alpha drink','limit':8,'authority':'lab','recipient':'synthetic-validation','model_revision':'gemma4-12b-bf16-negativeprefix-fixture-v1','runtime_profile':'gemma-bf16-tp2','encoding_revision':a.encoding_revision,'position_policy':'negative','cache_root':str(root/'real-reader-preparation-r1'),'compiler':[str(root/'venv/bin/python'),str(build/'distribution/service/gemma_compile.py'),'--model',str(root/'gemma4')],'host_memory_budget':32*1024**2}
config=root/'real-reader-preparation-config.json';config.write_text(json.dumps(c));env=os.environ.copy();env['AIMEE_NATIVE_LIBRARY']=a.publisher_library
report={'authority':'synthetic scoped publication through actual Go reader; actual private CPU model compiler'}
try:
 for name in ('first','reuse'):
  start=time.perf_counter();r=subprocess.run([str(build/'target/release/native-prepare'),str(config)],capture_output=True,text=True,env=env)
  report[name]={'seconds':time.perf_counter()-start,'exit_code':r.returncode,'stderr':r.stderr}
  if r.returncode:raise RuntimeError('private preparation failed; see report')
  result=json.loads(r.stdout);report[name]['result']=result;assert len(result['records'])==3
 assert report['reuse']['result']['reused'];report['status']='passed'
finally:pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
