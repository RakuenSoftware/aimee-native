"""Operator-only comparison on the private compiler host; synthetic records only.
No Aimee grant or GPU latency is implied. Requires the deployed worker/service.
Use a new output directory for every run to preserve prior evidence.
"""
import argparse,pathlib,json,subprocess,time,hashlib,shutil
p=argparse.ArgumentParser();p.add_argument("--output",required=True);p.add_argument("--facts-json");args=p.parse_args()
r=pathlib.Path(args.output);r.mkdir(parents=True,exist_ok=False)
original=json.loads(pathlib.Path('/opt/aimee-native-compiler/worker.json').read_text());original.pop('resident_socket',None);model=original['model_revision']
resident=dict(original,resident_socket='/run/aimee-native-compiler/compile.sock')
for name,config in [('oneshot',original),('resident',resident)]:
 path=pathlib.Path('/opt/aimee-native-compiler')/('benchmark-'+name+'.json');path.write_text(json.dumps(config));path.chmod(0o644)
 front={'command':['runuser','-u','aimee-compiler','--','/opt/aimee-memory-lab/venv/bin/python','/opt/aimee-native-compiler/remote_compile.py','worker','--config',str(path)]}
 (r/(name+'.json')).write_text(json.dumps(front))
cases=[['The verification vault code is 53728.','The verification project is named Willow.','The verification drink is chamomile tea.'],['The verification drink is chamomile tea.','The verification project is named Willow.','The verification vault code is 53728.'],['The verification vault code is 94613.','The verification project is named Aspen.','The verification drink is ginger tea.']]
if args.facts_json:cases=json.loads(pathlib.Path(args.facts_json).read_text())
report={'scope':'CPU preparation of synthetic complete ordered sets, not an authorization test','rows':[],'status':'running'}
for i,facts in enumerate(cases):
 request={'identity':{'model_revision':model,'records':[{'id':str(j)} for j in range(len(facts))]},'response':{'facts':[{'content':f} for f in facts]}}
 key=hashlib.sha256(json.dumps(request).encode()).hexdigest();row={'case':i,'records':len(facts),'modes':{}}
 for mode in (['oneshot','resident'] if i%2==0 else ['resident','oneshot']):
  out=r/(str(i)+'-'+mode)
  start=time.perf_counter()
  with (r/(str(i)+'-'+mode+'.log')).open('w') as log:
   subprocess.run(['/opt/aimee-memory-lab/venv/bin/python','/opt/aimee-native-compiler/remote_compile.py','frontend','--config',str(r/(mode+'.json')),'--output',str(out),'--identity',model,'--key',key],input=json.dumps(request).encode(),check=True,stdout=log,stderr=log,cwd="/tmp")
  elapsed=time.perf_counter()-start
  index=json.loads((out/'index.json').read_text());row['modes'][mode]={'elapsed_seconds':elapsed,'bytes':(out/'compact.pack').stat().st_size,'payload_sha256':index['dictionary_sha256'],'tokens':index['prototypes']}
 assert row['modes']['oneshot']['payload_sha256']==row['modes']['resident']['payload_sha256']
 assert (r/(str(i)+'-oneshot')/'index.json').read_bytes()==(r/(str(i)+'-resident')/'index.json').read_bytes()
 row['exact_match']=True;report['rows'].append(row);(r/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(row),flush=True)
report['status']='passed';(r/'report.json').write_text(json.dumps(report,indent=2)+'\n')
