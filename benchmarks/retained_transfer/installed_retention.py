"""Fresh installed 12B receiver; untrained joint-prefix delivery, no composition.

Separate mechanical and scored invocations. Source/runtime freeze is mandatory.
All serving payloads and outputs live in the campaign's NAS directory.
"""
import argparse,datetime,fcntl,hashlib,json,os,sys,time
from pathlib import Path
from canonical_store import CanonicalStore
from receiver_plan import SYSTEM,order,shuffled_records,record_for
from acquire_installed import sha

def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def append(stream,value):
 stream.write(json.dumps(value)+'\n');stream.flush();os.fsync(stream.fileno())
def prompt_ids(response):
 for chunk in response['chunks']:
  value=chunk.get('prompt_token_ids')
  if value is not None:return value
 raise RuntimeError('Stream did not return actual engine prompt token IDs')

def main():
 p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--mechanical-only',action='store_true')
 p.add_argument('--run-revision',choices=('r1','r2'),default='r1')
 p.add_argument('--repeat',type=int,choices=(1,2,3),default=1);args=p.parse_args();root=args.root
 assert str(root).startswith('/mnt/pve/backup/aimee-experiments/')
 suffix='' if args.run_revision=='r1' else '-'+args.run_revision
 rt=root/('installed-retention-runtime'+suffix);freeze=json.loads((root/('installed-retention-freeze'+suffix+'.json')).read_text())
 for name,digest in freeze['files'].items():assert sha(rt/name)==digest
 assert sha(Path(__file__))==freeze['driver_sha256']
 for name,digest in freeze['driver_files'].items():assert sha(Path(__file__).parent/name)==digest
 assert json.loads((root/'resumed-store-readback-audit.json').read_text())['passed']
 assert json.loads((root/'acquisition-audit.json').read_text())['passed']
 ended=json.loads((root/'learner-process-termination-r2.json').read_text());assert ended['canonical_admission_complete']
 if not args.mechanical_only:assert json.loads((root/('installed-retention-mechanical'+suffix)/'completion.json').read_text())['passed']
 out=root/('installed-retention-mechanical'+suffix if args.mechanical_only else 'receiver-gemma12b-r'+str(args.repeat))
 out.mkdir(exist_ok=False);block=out/'execution';block.mkdir()
 owner=CanonicalStore(root/'canonical-store-resumed-ready.json')
 accepted_rows=rows(root/'records.jsonl');controls=rows(root/'control-records.jsonl')
 with (out/'canonical-readback.jsonl').open('x') as receipts:
  for record in accepted_rows+controls:
   response=owner.call('/v1/memory/get',{'method':'memory.get','id':record['canonical_record_id']})
   assert response['status']=='ok' and response['memory']['content']==record['content']
   append(receipts,{'id':record['canonical_record_id'],'response':response})
 sys.path.insert(0,str(rt/'source'))
 import run_composition_main as serving
 import q5
 serving.SYSTEM=SYSTEM
 lock=open('/opt/jmlr-second-review-20261005/gpu-exclusive.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 import subprocess
 assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
 model=Path(serving.MODEL)
 pins={str(f.relative_to(model)):sha(f) for f in model.rglob('*') if f.is_file() and f.suffix in ('.gguf','.json','.safetensors')}
 assert pins==json.loads((root/'learner-weights-before-r2.json').read_text())
 service=None;count=0
 api={'http_port':18991,'api_key':'tmlr-local-fixture-only'}
 def request(item,memory=None,pub=None):
  system=SYSTEM if memory is None else SYSTEM+'\n\nAuthoritative memory:\n'+memory
  body={'model':serving.MODEL,'messages':[{'role':'system','content':system},
    {'role':'user','content':json.dumps(item,sort_keys=True)}],'temperature':0,'seed':20261011,'max_tokens':64,
    'stream':True,'stream_options':{'include_usage':True},'return_token_ids':True,'chat_template_kwargs':{'enable_thinking':False}}
  if pub:body['vllm_xargs']={'aimee_publication':pub}
  result=q5.stream(api,body)
  ids=prompt_ids(result)
  return result,body,ids
 def prepare(label,memory):
  started=time.perf_counter();pub,spec,seconds=service.prepare(label,[memory]);service.activate({pub:spec})
  index=json.loads((rt/'prepared'/pub/'index.json').read_text());bank=index['records'][spec['key']]['tokens']
  return pub,bank,{'prepare_seconds':seconds,'publication_seconds_total':time.perf_counter()-started,
    'publication':pub,'bank_tokens':len(bank),'physical_residency':serving.physical_summary(service.control({'op':'metrics'}))}
 try:
  service=serving.Service.__new__(serving.Service);serving.Service.__init__(service,rt,block,True)
  assert json.loads((block/'config.json').read_text())['tmlr_composition_enabled'] is False
  (out/'metadata.json').write_text(json.dumps({'session_id':'learner-B-'+str(service.process.pid),'pid':service.process.pid,
    'producer_pid':ended['pid'],'start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'checkpoint_files':pins,'runtime_freeze':freeze,'prefix_caching':False,'cpu_offload':0,
    'model':'installed Gemma4-12B Q4','untrained_joint_prefix':True,
    'physical_residency':serving.physical_summary(service.control({'op':'metrics'}))},indent=2))
  assert service.process.pid!=ended['pid']
  # Non-study warmup, excluded from scored outputs.
  request({'input':'Hello.'})
  if args.mechanical_only:
   checks=[]
   from transformers import AutoTokenizer
   tok=AutoTokenizer.from_pretrained(serving.MODEL,local_files_only=True)
   for size in (0,200,600):
    words=('neutral note '*size).split()
    memory='Record: the visitor badge is cobalt.\n'+' '.join(words)
    def length(value):return len(tok.apply_chat_template([{'role':'system','content':SYSTEM+'\n\nAuthoritative memory:\n'+value}],tokenize=True,add_generation_prompt=False,enable_thinking=False,return_dict=False))
    while length(memory)>900:
     words=words[:-8];memory='Record: the visitor badge is cobalt.\n'+' '.join(words)
    pub,bank,prep=prepare('mechanical:'+str(size),memory)
    item={'input':'What color is the visitor badge?'}
    native,nbody,nids=request(item,pub=pub);text,tb,tids=request(item,memory=memory)
    assert bank+nids==tids,'Exact full-prefix token reconstruction failed'
    checks.append({'padding_repetitions':size,'native':native,'text':text,'bank_tokens':bank,
      'native_request':nbody,'text_request':tb,'exact_token_identity':True,'preparation':prep,
      'output_agreement':native['answer']==text['answer']})
    service.activate({})
   (out/'checks.json').write_text(json.dumps(checks,indent=2))
  else:
   families=rows(root/'fixture/evaluation/families.jsonl');training={f['family_id']:f for f in rows(root/'fixture/learner/families.jsonl')}
   accepted={x['family_id']:x for x in accepted_rows};first={x['family_id']:x for x in controls if x['control']=='Unvalidated'}
   oracle={x['family_id']:x for x in controls if x['control']=='Oracle'};shuffled=shuffled_records(accepted_rows)
   with (out/'responses.jsonl').open('x') as stream,(out/'preparations.jsonl').open('x') as preparations:
    for family,arms in order(families,args.repeat):
     paired={}
     for arm in arms:
      fid=family['family_id'];record=oracle[fid] if arm=='Oracle' else record_for(arm,family,accepted,first,shuffled)
      lex='Lexicon:\n'+json.dumps(family['lexicon'],sort_keys=True)
      memory=lex
      if record is not None:memory+='\nRule:\n'+record['content']
      if arm=='Replay':memory+='\nExperience:\n'+json.dumps(training[fid]['examples'],sort_keys=True)
      native=arm in ('Native','Oracle','Unvalidated','Shuffled') and record is not None
      pub=None;bank=[];prep=None
      if native:
       pub,bank,prep=prepare(fid+'/'+arm+'/r'+str(args.repeat),memory)
       append(preparations,{'family_id':fid,'arm':arm,'record_id':record['canonical_record_id'],'preparation':prep})
      for item in family['inputs']:
       payload={'language':family['language'],'lexicon':family['lexicon'],'input':item['input'],'slots':item['slots']}
       result,body,ids=request(payload,memory=None if native else memory,pub=pub)
       row={'receiver':'google/gemma-4-12B-it','arm':arm,'repeat':args.repeat-1,'family_id':fid,'input_id':item['id'],
         'session_id':'learner-B-'+str(service.process.pid),'output':result['answer'],'score':int(result['answer']==item['output']),
         'expected':item['output'],'ttft_ms':result['first_content_seconds']*1000 if result['first_content_seconds'] is not None else None,
         'end_to_end_ms':result['complete_seconds']*1000,'prompt_tokens':len(ids),'prefill_tokens':len(ids),
         'prompt_token_ids':ids,'native_prefix_token_ids':bank,'request':body,'response':result,
         'canonical_record_id':record['canonical_record_id'] if record else None,'preparation':prep}
       append(stream,row);count+=1
       if arm in ('Native','Text'):paired[arm,item['id']]=row
      if native:service.activate({})
     for item in family['inputs']:
      n=paired['Native',item['id']];t=paired['Text',item['id']]
      assert n['native_prefix_token_ids']+n['prompt_token_ids']==t['prompt_token_ids']
     print(json.dumps({'family_id':fid,'responses':count}),flush=True)
   assert count==8400
  after={str(f.relative_to(model)):sha(f) for f in model.rglob('*') if f.is_file() and f.suffix in ('.gguf','.json','.safetensors')}
  assert after==pins
  (out/'completion.json').write_text(json.dumps({'passed':True,'mechanical_only':args.mechanical_only,'responses':count,
    'weights_unchanged':True,'end_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2))
 finally:
  if service is not None:
   service.stop()
   (out/'process-termination.json').write_text(json.dumps({'pid':service.process.pid,'exit_code':service.process.poll()},indent=2))
if __name__=='__main__':main()
