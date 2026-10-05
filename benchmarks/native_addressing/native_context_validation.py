"""Frozen instruction-bound prefix regression and fresh implicit-alias gate.

Run in an isolated transient service. Uses the real reader and public fixtures;
never stops another workload. Offline preparation and strict serving are separate.
"""
import argparse, hashlib, json, subprocess, time
from pathlib import Path
from campaign import SYSTEM,new_json
from hybrid_validation import REVISION

def capacity():
 """Require the intended, idle CUDA accelerator before starting a stage."""
 result=subprocess.run(['nvidia-smi','--id=0','--query-gpu=name,memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True,check=True)
 name,used=result.stdout.strip().rsplit(',',1)
 if 'RTX 5080' not in name or int(used.strip())>1024:
  raise RuntimeError('RTX 5080 unavailable or busy: '+result.stdout.strip())

def main(a):
 root=Path(a.output);root.mkdir(mode=0o700)
 common=['--binary',a.binary,'--model',a.model,'--placement',a.placement,'--reader',a.reader,'--archive',a.archive,'--hybrid','--encoding','system-message','--tasks',a.tasks,'--turns','0','16','48']
 hardware=subprocess.run(['nvidia-smi','--id=0','--query-gpu=name,uuid,memory.total,driver_version','--format=csv,noheader'],capture_output=True,text=True,check=True).stdout.strip()
 new_json(root/'plan.json',{'profile':'complete-hybrid-system-message-v1','system_context':SYSTEM,'tasks_sha256':hashlib.sha256(Path(a.tasks).read_bytes()).hexdigest(),'accelerator':hardware,'placement':json.loads(Path(a.placement).read_text()),'placement_sha256':hashlib.sha256(Path(a.placement).read_bytes()).hexdigest(),'stages':['online','offline-prepare','strict-prepared'],'gate':'original regressions plus original implicit-alias failures plus fresh implicit aliases; all answers, canonical selection, budgets; no added alias identity facts'})
 def campaign(name,prepared=None):
  capacity();cmd=[a.python,str(Path(__file__).with_name('published_campaign.py')),'--output',str(root/name),*common]
  if prepared:cmd+=['--prepared',str(prepared),'--revision',REVISION]
  print('START '+name,flush=True)
  with (root/(name+'.log')).open('xb') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
  result=json.loads((root/name/'results.json').read_text())
  assert result['n']==432 and result['correct']==432 and result['selection_correct']==432,result
  for row in result['rows']:
   trace=json.loads((root/name/row['trace']).read_text())
   assert trace['memory_prompt_tokens']==0 and trace['native_recurrent_state'] is True and trace['memory_encoding']=='system-message'
   assert trace['native_memory_metrics']['positioning']=='native-prefix-absolute-v1'
   assert trace['native_system_context_sha256']==hashlib.sha256(SYSTEM.encode()).hexdigest()
   if prepared:assert trace['memory_encoding_passes']==0
  print('PASS '+name+' 432',flush=True)
 campaign('online')
 tasks=json.loads(Path(a.tasks).read_text())['tasks'];reader=subprocess.Popen([a.reader,'serve-published','--root',a.archive],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 requests=[];seen=set()
 try:
  reader.stdin.write('{"op":"pin"}\n');reader.stdin.flush();json.loads(reader.stdout.readline())
  for task in tasks:
   reader.stdin.write(json.dumps({'op':'recall','query':task['query'],'limit':6,'authority':'public-research'})+'\n');reader.stdin.flush()
   refs=[f['memory_ref'] for f in json.loads(reader.stdout.readline()).get('response',{}).get('facts',[])]
   key=json.dumps(refs,sort_keys=True)
   if refs and key not in seen:requests.append({'query':task['query'],'expected_refs':refs,'system_context':SYSTEM});seen.add(key)
 finally:reader.stdin.close();reader.wait(timeout=10)
 assert len(requests)==18
 reqpath=root/'prepare-requests.json';new_json(reqpath,requests);prepared=Path(a.prepared_output) if a.prepared_output else root/'prepared'
 # All relevant exact selections are local; a nonexistent remote socket is a
 # terminal preparation miss, never a source of manufactured facts.
 cmd=[a.binary,'prepare-memory','--model',a.model,'--placement',a.placement,'--int8','--image-reader',a.reader,'--memory-image',a.archive,'--read-gateway',str(root/'no-remote.sock'),'--read-authority','public-research','--trace-dir',str(root/'prepare-traces'),'--requests',str(reqpath),'--prepared-memory',str(prepared),'--prepared-model-revision',REVISION,'--enable-hybrid-native','--native-candidate-routing','--memory-limit','6','--max-active-records','6','--memory-encoding','system-message']
 capacity();new_json(root/'prepare-invocation.json',{'argv':cmd});print('START offline-prepare',flush=True)
 with (root/'prepare.log').open('xb') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
 index=json.loads((prepared/'index.json').read_text());entries=index['entries'];assert len(entries)==36
 payloads={e['recurrent']['payload'] for e in entries.values()};assert len(payloads)==18
 actual=sum((prepared/p).stat().st_size for p in payloads);duplicated=sum(e['recurrent']['bytes'] for e in entries.values())
 assert actual*2==duplicated
 new_json(root/'prepared-storage.json',{'entries':36,'distinct_recurrent_payloads':18,'actual_recurrent_bytes':actual,'entry_sum_recurrent_bytes':duplicated,'saved_bytes':duplicated-actual,'ratio':actual/duplicated})
 print('PASS offline-prepare; exact recurrence storage halved',flush=True)
 campaign('strict-prepared',prepared)
 print('PASS all instruction-bound native prefix gates',flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('output','binary','model','placement','reader','archive','tasks','python'):p.add_argument('--'+key,required=True)
 p.add_argument('--prepared-output',help='Optional separate filesystem for lossless prepared payloads')
 main(p.parse_args())
