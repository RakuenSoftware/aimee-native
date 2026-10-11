"""Fresh-process seven-arm HF receiver. Requires completed acquisition and controls.

Not a driver for the installed quantized 12B profile. No study input is scored
unless the exact receiver profile has passed its non-study mechanical gate.
"""
import argparse,datetime,fcntl,hashlib,json,os,subprocess,time
from pathlib import Path
from canonical_store import UnixHTTP
from prefix_receiver import PrefixReceiver
from receiver_plan import messages,record_for,shuffled_records,order,common_prefix

def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def append(stream,value):
    stream.write(json.dumps(value)+'\n');stream.flush();os.fsync(stream.fileno())
def readback(socket,record):
    conn=UnixHTTP(socket)
    try:
        conn.request('POST','/v1/memory/get',json.dumps({'method':'memory.get','id':record['canonical_record_id']}),headers={'Content-Type':'application/json'})
        response=conn.getresponse();value=json.loads(response.read())
        assert response.status==200 and value['status']=='ok'
        assert value['memory']['content']==record['content']
        assert hashlib.sha256(record['content'].encode()).hexdigest()==record['content_sha256']
        return value
    finally:conn.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--model-id',required=True);p.add_argument('--name',required=True)
    p.add_argument('--repeat',type=int,choices=(1,2,3),required=True);p.add_argument('--execution-freeze',type=Path,required=True)
    args=p.parse_args();root=args.root
    assert str(root).startswith('/mnt/pve/backup/aimee-experiments/')
    frozen=json.loads(args.execution_freeze.read_text())
    for name,digest in frozen['files'].items():assert sha(Path(__file__).parent/name)==digest
    assert json.loads((root/'acquisition-audit.json').read_text())['passed']
    ended=json.loads((root/'learner-process-termination-r2.json').read_text())
    assert ended['canonical_admission_complete'] and ended['exit_code'] is not None
    assert ended['pid']!=os.getpid()
    mechanical=json.loads((root/('mechanical-'+args.name)/'completion.json').read_text())
    assert mechanical['passed'] and mechanical['model']==str(args.model)
    fixture=json.loads((root/'fixture/freeze.json').read_text())
    for name,digest in fixture['files'].items():assert sha(root/'fixture'/name)==digest
    families=rows(root/'fixture/evaluation/families.jsonl')
    training={x['family_id']:x for x in rows(root/'fixture/learner/families.jsonl')}
    records=rows(root/'records.jsonl');accepted={x['family_id']:x for x in records}
    # Controls must be separately canonicalized and labeled, never replaced by
    # accepted records or passed off as learned acquisitions.
    controls=rows(root/'control-records.jsonl')
    first={x['family_id']:x for x in controls if x['control']=='Unvalidated'}
    oracles={x['family_id']:x for x in controls if x['control']=='Oracle'}
    assert set(oracles)=={f['family_id'] for f in families}
    assert all(oracles[f['family_id']]['content']==f['oracle_rule'] for f in families)
    shuffle=shuffled_records(records)
    identity=json.loads((root/'canonical-store-ready-r3.json').read_text())
    assert identity['private_experiment_instance'] is True
    out=root/('receiver-'+args.name+'-r'+str(args.repeat));out.mkdir(exist_ok=False)
    with (out/'canonical-readback.jsonl').open('x') as receipts:
        for record in records+controls:append(receipts,{'id':record['canonical_record_id'],'readback':readback(identity['http_socket'],record)})
    lock=open('/opt/jmlr-second-review-20261005/gpu-exclusive.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
    before={str(p.relative_to(args.model)):sha(p) for p in args.model.rglob('*') if p.is_file() and p.suffix in ('.json','.safetensors')}
    receiver=PrefixReceiver(args.model);torch=receiver.torch
    session='receiver-'+args.name+'-'+str(os.getpid())
    (out/'metadata.json').write_text(json.dumps({'session_id':session,'pid':os.getpid(),
        'start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'receiver':args.model_id,
        'repeat':args.repeat-1,'process_repetition_label':args.repeat,'checkpoint_files':before,'execution_freeze':frozen,
        'dtype':'BF16','model_class':type(receiver.model).__name__,'config':receiver.model.config.to_dict(),
        'torch':torch.__version__,'gpu':torch.cuda.get_device_name(),'prefix_caching':False,
        'all_weights_cuda':True,'trainable_parameter_count':0,'no_tool_or_file_access_for_model':True,
        'producer_pid':ended['pid'],'energy_joules':'not measured'},indent=2))
    for _ in range(3):receiver.answer(receiver.full_tokens([{'role':'user','content':'Hello.'}]))
    count=0
    with (out/'responses.jsonl').open('x') as response_stream,(out/'preparations.jsonl').open('x') as prep_stream:
        for family,arms in order(families,args.repeat):
            for arm in arms:
                record=oracles[family['family_id']] if arm=='Oracle' else record_for(arm,family,accepted,first,shuffle)
                native=arm in ('Native','Oracle','Unvalidated','Shuffled') and record is not None
                planning_start=time.perf_counter()
                plans=[messages(family,item,arm,record,training[family['family_id']]) for item in family['inputs']]
                full=[receiver.full_tokens(m) for m in plans];prefix=[]
                if native:
                    # Define the bank boundary using synthetic tokenizer probes,
                    # never by a common prefix of the held-out task phrases.
                    probes=[messages(family,{'input':v,'slots':{}},arm,record,training[family['family_id']]) for v in ('AAAA boundary probe','ZZZZ boundary probe')]
                    prefix=common_prefix([receiver.full_tokens(m) for m in probes])
                    while prefix and not all(ids[:len(prefix)]==prefix for ids in full):prefix=prefix[:-1]
                planning_ms=(time.perf_counter()-planning_start)*1000
                key=family['family_id']+'/'+arm
                preparation=None
                if native:
                    assert prefix and all(len(ids)>len(prefix) for ids in full)
                    preparation=receiver.prepare(key,prefix)
                    append(prep_stream,{'family_id':family['family_id'],'arm':arm,'record_id':record['canonical_record_id'],
                        'content_sha256':record['content_sha256'],'preparation':preparation,'family_planning_ms':planning_ms,
                        'scope':'Includes fixed instruction/lexicon and the record, not record-only encoding.'})
                for item,planned,full_ids in zip(family['inputs'],plans,full):
                    torch.cuda.synchronize();started=time.perf_counter()
                    request_messages=messages(family,item,arm,None if native else record,training[family['family_id']])
                    task_payload={'messages':request_messages}
                    if native:task_payload['record_id']=record['canonical_record_id']
                    request_text=json.dumps(task_payload,sort_keys=True)
                    task_prompt_ids=receiver.full_tokens(request_messages)
                    # Token identities are compiled in the family planning pass,
                    # for both arms. No task KV is prepared or reused.
                    execution_ids=full_ids[len(prefix):] if native else full_ids
                    assert not native or prefix+execution_ids==full_ids
                    if native:assert record['content'] not in request_text
                    frontend_ms=(time.perf_counter()-started)*1000
                    result=receiver.answer(execution_ids,key if native else None)
                    count+=1
                    append(response_stream,dict(result,receiver=args.model_id,arm=arm,repeat=args.repeat-1,
                        input_id=item['id'],family_id=family['family_id'],language=family['language'],session_id=session,
                        score=int(result['output']==item['output']),expected=item['output'],
                        ttft_ms=frontend_ms+result['engine_ttft_ms'],end_to_end_ms=frontend_ms+result['engine_end_ms'],
                        frontend_ms=frontend_ms,family_planning_ms=planning_ms,token_compilation_scope='Both arms compiled in the separately logged family planning pass; frontend timing tokenizes the actual task request.',prompt_tokens=len(task_prompt_ids),task_prompt_token_ids=task_prompt_ids,
                        full_text_token_ids=full_ids,native_prefix_token_ids=prefix,request_text=request_text,
                        canonical_record_id=record['canonical_record_id'] if record is not None else None,
                        matching_record_available=family['family_id'] in accepted,occupied_shuffled=family['family_id'] in shuffle,
                        resident_bank_bytes=preparation['state']['logical_bytes'] if preparation else 0))
                if native:receiver.retire(key)
            print(json.dumps({'family_id':family['family_id'],'responses':count}),flush=True)
    after={str(p.relative_to(args.model)):sha(p) for p in args.model.rglob('*') if p.is_file() and p.suffix in ('.json','.safetensors')}
    assert before==after and count==8400
    (out/'completion.json').write_text(json.dumps({'passed':True,'responses':count,'weights_unchanged':True,
        'pid':os.getpid(),'end_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2))
if __name__=='__main__':main()
