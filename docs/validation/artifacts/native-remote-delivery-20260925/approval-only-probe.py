import json,pathlib,subprocess,os,time
lab=pathlib.Path('/opt/aimee-memory-lab');build=lab/'vllm-native-build';work=lab/'preparation-check-r1';work.mkdir(exist_ok=False)
r=subprocess.run([str(lab/'aimee-selection-fixture'),'--root',str(work/'source')],capture_output=True,text=True,check=True);source=json.loads(r.stdout)
c=json.loads((lab/'real-reader-preparation-config.json').read_text());c.update(memory_image=source['root'],cache_root=str(work/'cache'))
p=work/'config.json';p.write_text(json.dumps(c));env=os.environ.copy();env['AIMEE_NATIVE_LIBRARY']=str(lab/'aimee-qwen/target/release/libaimee_qwen.so')
report={'authority':'fresh synthetic scoped publication; actual reader and CPU compiler; approval-only mode executes no compiler'}
try:
 start=time.perf_counter();r=subprocess.run([str(build/'target/release/native-prepare'),str(p)],capture_output=True,text=True,env=env);assert r.returncode==0,r.stderr;prepared=json.loads(r.stdout);report['preparation_seconds']=time.perf_counter()-start;report['prepared']=prepared
 c['compiler']=['/this/compiler/does/not/exist'];c['cache_root']=str(work/'must-not-exist');p.write_text(json.dumps(c))
 start=time.perf_counter();r=subprocess.run([str(build/'target/release/native-prepare'),str(p),'--check'],capture_output=True,text=True,env=env);assert r.returncode==0,r.stderr;checked=json.loads(r.stdout)
 assert checked['key']==prepared['key'] and checked['records']==prepared['records'] and len(checked['records'])==3
 assert not (work/'must-not-exist').exists();report['approval_only_seconds']=time.perf_counter()-start;report['approved']=checked;report['status']='passed'
finally:(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
