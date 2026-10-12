"""Secondary request-scope study on every admitted record, without new learning.

Seven records imply seven turns, not ten. Three conditions use the same current
rule prefix. PersistentText carries previous rule blocks into reconstructed
history; RemovedText and Native retain only public tasks and generated answers.
No prompt/task KV caching. Native banks are prepared once per receiver session.
"""
import argparse,datetime,fcntl,hashlib,json,os,random,subprocess,time
from pathlib import Path
from prefix_receiver import PrefixReceiver,cache_tensors
from receiver_plan import SYSTEM,common_prefix
from score_receiver import rows,sha,append,readback

ARMS=('Native','PersistentText','RemovedText')

def fixed_system(family,record=None):
 text=SYSTEM+'\nLanguage: '+family['language']+'\nLexicon: '+json.dumps(family['lexicon'],sort_keys=True)
 if record is not None:text+='\nRule:\n'+record['content']
 return text

def task_text(family,item):
 return json.dumps({'language':family['language'],'input':item['input'],'slots':item['slots']},sort_keys=True)

def history_messages(history,persistent):
 output=[]
 for turn in history:
  user=turn['task']
  if persistent:user='Retained memory from this earlier turn:\n'+turn['record']+'\nTask:\n'+user
  output.extend([{'role':'user','content':user},{'role':'assistant','content':turn['answer']}])
 return output

def storage_bytes(caches):
 storage={}
 for cache in caches:
  for _,tensor in cache_tensors(cache):
   assert tensor.device.type=='cuda'
   s=tensor.untyped_storage();storage[s.data_ptr()]=s.nbytes()
 return sum(storage.values())

class MeasuredReceiver(PrefixReceiver):
 def forward(self,ids,cache=None):
  result=super().forward(ids,cache)
  # Metadata inspection only; no copies, casts or changes to execution state.
  self.last_task_cache_bytes=storage_bytes([result.past_key_values])
  return result

def main():
 p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--name',required=True)
 p.add_argument('--model',type=Path,required=True);p.add_argument('--model-id',required=True)
 p.add_argument('--repeat',type=int,choices=(1,2,3),required=True);p.add_argument('--execution-freeze',type=Path,required=True)
 args=p.parse_args();root=args.root
 assert str(root).startswith('/mnt/pve/backup/aimee-experiments/')
 freeze=json.loads(args.execution_freeze.read_text())
 for name,digest in freeze['files'].items():assert sha(Path(__file__).parent/name)==digest
 assert json.loads((root/'acquisition-audit.json').read_text())['passed']
 assert json.loads((root/'mechanical-r3'/('mechanical-'+args.name)/'completion.json').read_text())['passed']
 families={f['family_id']:f for f in rows(root/'fixture/evaluation/families.jsonl')}
 records={r['family_id']:r for r in rows(root/'records.jsonl')}
 assert records and len(records)<=10
 identity=json.loads((root/'canonical-store-resumed-ready.json').read_text())
 out=root/('context-growth-'+args.name+'-r'+str(args.repeat));out.mkdir(exist_ok=False)
 with (out/'canonical-readback.jsonl').open('x') as receipts:
  for record in records.values():append(receipts,readback(identity['http_socket'],record))
 lock=open('/opt/jmlr-second-review-20261005/gpu-exclusive.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
 pins={str(p.relative_to(args.model)):sha(p) for p in args.model.rglob('*') if p.is_file() and p.suffix in ('.json','.safetensors')}
 assert pins==json.loads((root/('calibration-'+args.name+'-r1')/'metadata.json').read_text())['checkpoint_files']
 receiver=MeasuredReceiver(args.model);torch=receiver.torch
 for _ in range(3):receiver.answer(receiver.full_tokens([{'role':'user','content':'Hello.'}]))
 (out/'metadata.json').write_text(json.dumps({'pid':os.getpid(),'start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
  'model_id':args.model_id,'repeat':args.repeat-1,'checkpoint_files':pins,'execution_freeze':freeze,
  'turns_per_episode':len(records),'episodes_per_arm':20,'all_admitted_records_used':True,
  'caching_disabled':True,'native_profile':'current-record complete prefix before reconstructed public history; no mid-turn hot-plug claim',
  'transcript_policy':'Generated answers retained in all arms; only PersistentText serializes earlier private rule blocks into reconstructed history.',
  'native_residency':'All prepared banks on GPU; only the selected bank is bound to each request.',
  'no_additional_training':True,'energy_joules':'not measured'},indent=2))
 rng=random.Random('linked-context-arms-'+str(args.repeat));arms=list(ARMS);rng.shuffle(arms)
 count=0
 with (out/'responses.jsonl').open('x') as output,(out/'preparations.jsonl').open('x') as preps:
  for arm in arms:
   banks={};prepared_wall=0
   if arm=='Native':
    for fid,record in sorted(records.items()):
     f=families[fid];sys=fixed_system(f,record)
     probes=[receiver.full_tokens([{'role':'system','content':sys},{'role':'user','content':v}]) for v in ('AAAA','ZZZZ','{')]
     prefix=common_prefix(probes)
     assert prefix
     torch.cuda.synchronize();started=time.perf_counter();info=receiver.prepare(fid,prefix);torch.cuda.synchronize()
     wall=time.perf_counter()-started;prepared_wall+=wall;banks[fid]=prefix
     append(preps,{'family_id':fid,'canonical_record_id':record['canonical_record_id'],'full_preparation_wall_seconds':wall,
       'model_prefill_seconds':info['seconds'],'forensic_hashing_included_in_full_wall':True,'native_state':info['state'],'prefix_tokens':len(prefix)})
   resident_bytes=storage_bytes([v['cache'] for v in receiver.prepared.values()])
   for episode in range(20):
    fids=sorted(records);random.Random('linked-context-order-'+str(args.repeat)+'-'+str(episode)).shuffle(fids)
    history=[]
    for turn,fid in enumerate(fids,1):
     f=families[fid];record=records[fid];item=f['inputs'][episode]
     started=time.perf_counter();public=history_messages(history,arm=='PersistentText')
     user=task_text(f,item)
     full_messages=[{'role':'system','content':fixed_system(f,record)},*public,{'role':'user','content':user}]
     full_ids=receiver.full_tokens(full_messages)
     api_messages=full_messages if arm!='Native' else [{'role':'system','content':fixed_system(f)},*public,{'role':'user','content':user}]
     api_ids=receiver.full_tokens(api_messages)
     prefix=banks[fid] if arm=='Native' else []
     assert not prefix or full_ids[:len(prefix)]==prefix
     suffix=full_ids[len(prefix):]
     assert prefix+suffix==full_ids
     assert len(full_ids)+64<=receiver.config.max_position_embeddings
     stripped=[{'role':'system','content':fixed_system(f,record)},*history_messages(history,False),{'role':'user','content':user}]
     carried_delta=len(full_ids)-len(receiver.full_tokens(stripped))
     frontend_ms=(time.perf_counter()-started)*1000
     result=receiver.answer(suffix,fid if arm=='Native' else None)
     task_cache=receiver.last_task_cache_bytes;count+=1
     append(output,dict(result,receiver=args.model_id,arm=arm,repeat=args.repeat-1,episode=episode,turn=turn,
       family_id=fid,input_id=item['id'],canonical_record_id=record['canonical_record_id'],expected=item['output'],
       score=int(result['output']==item['output']),prompt_tokens=len(api_ids),full_execution_tokens=len(full_ids),
       ttft_ms=frontend_ms+result['engine_ttft_ms'],end_to_end_ms=frontend_ms+result['engine_end_ms'],frontend_ms=frontend_ms,
       explicit_previous_memory_blocks=len(history) if arm=='PersistentText' else 0,carried_memory_token_delta=carried_delta,
       indirect_record_echo_in_public_answers=any(r['content'] in h['answer'] for r in records.values() for h in history),
       prepared_bank_resident_bytes=resident_bytes,task_cache_end_bytes=task_cache,
       task_cache_byte_seconds_upper_proxy=task_cache*result['engine_end_ms']/1000,
       byte_seconds_scope='end-cache bytes times engine duration; proxy, not an exact allocation-time integral',
       preparation_total_seconds=prepared_wall,full_messages=full_messages if arm!='Native' else None,request_messages=api_messages))
     history.append({'task':user,'answer':result['output'],'record':record['content']})
   if arm=='Native':
    for fid in banks:receiver.retire(fid)
  assert count==len(records)*20*3
 assert pins=={str(p.relative_to(args.model)):sha(p) for p in args.model.rglob('*') if p.is_file() and p.suffix in ('.json','.safetensors')}
 (out/'completion.json').write_text(json.dumps({'passed':True,'responses':count,'weights_unchanged':True,
   'end_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2))
if __name__=='__main__':main()
