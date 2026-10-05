"""Frozen complete-hybrid validation, including strict offline-prepared serving.
Runs isolated research processes and waits for GPU capacity. For long remote
runs, launch it under a transient service rather than an attached shell.
"""
import argparse,hashlib,json,os,shutil,socketserver,subprocess,threading,time
from pathlib import Path
from published_campaign import EmptyFallback
from campaign import new_json
REVISION='1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0'
def capacity():
 while any(int(p.read_text())>1024**3 for p in Path('/sys/class/drm').glob('card[0-9]*/device/mem_info_vram_used')):
  time.sleep(15)
def main(a):
 root=Path(a.output);root.mkdir(mode=0o700)
 common=['--binary',a.binary,'--model',a.model,'--placement',a.placement,'--reader',a.reader,'--hybrid']
 jobs=[('development',a.archive,None,[0,16]),('holdout',a.holdout_archive,a.holdout,[0,16,48])]
 new_json(root/'plan.json',{'profile':'complete-hybrid-content-v1','revision':REVISION,'jobs':jobs,'stages':['online','offline-prepare','strict-prepared'],'gate':'all exact answers and canonical selection; no serving encoding; immutable source and derived state; no memory prompt tokens'})
 def campaign(name,archive,tasks,turns,prepared=None):
  capacity();cmd=[a.python,str(Path(__file__).with_name('published_campaign.py')),'--output',str(root/name),'--archive',archive,*common,'--turns',*map(str,turns)]
  if tasks:cmd+=['--tasks',tasks]
  if prepared:cmd+=['--prepared',str(prepared),'--revision',REVISION]
  print('START '+name,flush=True)
  with open(root/(name+'.log'),'xb') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
  result=json.loads((root/name/'results.json').read_text());assert result['correct']==result['n'] and result['selection_correct']==result['n'],result
  if prepared:
   for row in result['rows']:
    trace=json.loads((root/name/row['trace']).read_text());assert trace['memory_encoding_passes']==0
  print('PASS '+name+' '+str(result['n']),flush=True)
 for name,archive,tasks,turns in jobs:
  if name=='development' and a.reuse_development:
   previous=Path(a.reuse_development);protocol=json.loads((previous/'protocol.json').read_text());result=json.loads((previous/'results.json').read_text())
   assert protocol['archive']==archive and protocol['profile']=='complete-hybrid-content-v1' and protocol['binary_sha256']==hashlib.sha256(Path(a.binary).read_bytes()).hexdigest()
   assert result['n']==96 and result['correct']==96 and result['selection_correct']==96
   shutil.copytree(previous,root/(name+'-online'),ignore=lambda directory,names:[n for n in names if not (Path(directory)/n).is_file() and not (Path(directory)/n).is_dir()]);new_json(root/'reused-development.json',{'source':str(previous),'results_sha256':hashlib.sha256((previous/'results.json').read_bytes()).hexdigest()});print('REUSE development-online 96 verified',flush=True)
  else:campaign(name+'-online',archive,tasks,turns)
 for name,archive,tasks,turns in jobs:
  task_rows=json.loads((root/(name+'-online')/'protocol.json').read_text())['tasks']
  reader=subprocess.Popen([a.reader,'serve-published','--root',archive],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
  requests=[];seen=set()
  try:
   reader.stdin.write('{"op":"pin"}\n');reader.stdin.flush();json.loads(reader.stdout.readline())
   for task in task_rows:
    reader.stdin.write(json.dumps({'op':'recall','query':task['query'],'limit':6,'authority':'public-research'})+'\n');reader.stdin.flush()
    facts=json.loads(reader.stdout.readline()).get('response',{}).get('facts',[]);refs=[f['memory_ref'] for f in facts];key=json.dumps(refs,sort_keys=True)
    if refs and key not in seen:requests.append({'query':task['query'],'expected_refs':refs});seen.add(key)
  finally:reader.stdin.close();reader.wait(timeout=10)
  reqpath=root/(name+'-prepare-requests.json');new_json(reqpath,requests)
  prepared=root/(name+'-prepared');gateway=str(root/(name+'-prepare.sock'));server=socketserver.UnixStreamServer(gateway,EmptyFallback);threading.Thread(target=server.serve_forever,daemon=True).start()
  cmd=[a.binary,'prepare-memory','--model',a.model,'--placement',a.placement,'--int8','--image-reader',a.reader,'--memory-image',archive,'--read-gateway',gateway,'--read-authority','public-research','--trace-dir',str(root/(name+'-prepare-traces')),'--requests',str(reqpath),'--prepared-memory',str(prepared),'--prepared-model-revision',REVISION,'--enable-hybrid-native','--native-candidate-routing','--memory-limit','6','--max-active-records','6']
  try:
   capacity();new_json(root/(name+'-prepare-invocation.json'),{'argv':cmd});print('START '+name+'-prepare',flush=True)
   with open(root/(name+'-prepare.log'),'xb') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
  finally:server.shutdown();server.server_close()
  index=json.loads((prepared/'index.json').read_text());assert index['entries'] and all(e.get('recurrent') for e in index['entries'].values());print('PASS '+name+'-prepare',flush=True)
  campaign(name+'-strict-prepared',archive,tasks,turns,prepared)
 print('PASS all complete-hybrid gates',flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for key in ['output','binary','model','placement','reader','archive','holdout-archive','holdout','python']:p.add_argument('--'+key,required=True)
 p.add_argument('--reuse-development')
 main(p.parse_args())
