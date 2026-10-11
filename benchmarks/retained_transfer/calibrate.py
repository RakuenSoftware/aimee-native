"""No-record calibration on separate inputs, before any learner acquisition."""
import argparse,datetime,fcntl,hashlib,json,os,subprocess,time
from pathlib import Path

SYSTEM='Translate the English phrase into the invented language. Use the supplied lexicon. Return only the translated phrase, without explanation.'

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--model-id',required=True);p.add_argument('--execution-freeze',type=Path);args=p.parse_args()
    assert str(args.out).startswith('/mnt/pve/backup/aimee-experiments/')
    freeze=json.loads((args.fixture/'freeze.json').read_text())
    for relative,sha in freeze['files'].items():assert digest(args.fixture/relative)==sha
    if args.execution_freeze:
        execution=json.loads(args.execution_freeze.read_text())
        assert digest(Path(__file__))==execution['calibration_source_sha256']
    families=[json.loads(x) for x in (args.fixture/'calibration/families.jsonl').read_text().splitlines()]
    args.out.mkdir(parents=True,exist_ok=False)
    lock=open('/opt/jmlr-second-review-20261005/gpu-exclusive.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
    import torch,transformers
    from transformers import AutoTokenizer,AutoConfig,AutoModelForCausalLM,AutoModelForImageTextToText
    torch.set_num_threads(4);torch.manual_seed(20261011)
    pins={str(f.relative_to(args.model)):digest(f) for f in args.model.rglob('*') if f.is_file() and f.suffix in ('.safetensors','.json')}
    tok=AutoTokenizer.from_pretrained(args.model,local_files_only=True)
    def inputs(family,item):
        messages=[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps({'language':family['language'],
             'lexicon':family['lexicon'],'input':item['input'],'slots':item['slots']},sort_keys=True)}]
        ids=tok.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)
        if not isinstance(ids,list):ids=ids['input_ids']
        return messages,ids
    maximum=max(len(inputs(f,x)[1]) for f in families for x in f['inputs'])
    (args.out/'token-preflight.json').write_text(json.dumps({'maximum_prompt_tokens':maximum,'response_cap':64})+'\n')
    config=AutoConfig.from_pretrained(args.model,local_files_only=True)
    model_class=AutoModelForImageTextToText if config.model_type in ('gemma4','qwen3_5') else AutoModelForCausalLM
    model=model_class.from_pretrained(args.model,local_files_only=True,dtype=torch.bfloat16,attn_implementation='sdpa').to('cuda').eval()
    text_config=model.config.get_text_config()
    model.requires_grad_(False)
    assert all(p.device.type=='cuda' and not p.requires_grad for p in model.parameters())
    assert maximum+64<=text_config.max_position_embeddings
    metadata={'model_id':args.model_id,'checkpoint_files':pins,'dtype':'BF16','torch':torch.__version__,
      'transformers':transformers.__version__,'gpu':torch.cuda.get_device_name(),'pid':os.getpid(),
      'start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_commit':execution['commit'] if args.execution_freeze else freeze['commit'],
      'model_class':type(model).__name__,'all_weights_cuda':True,'trainable_parameter_count':0,'prefix_caching':False,'model_config':model.config.to_dict()}
    (args.out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    with torch.inference_mode(),(args.out/'responses.jsonl').open('x') as stream:
        # Warm-up has no study inputs and is excluded.
        ids=tok.encode('Hello',return_tensors='pt').to('cuda')
        for _ in range(3):model.generate(ids,max_new_tokens=2,do_sample=False,pad_token_id=tok.eos_token_id)
        del ids
        for family in families:
            for item in family['inputs']:
                messages,ids=inputs(family,item);tensor=torch.tensor([ids],device='cuda');mask=torch.ones_like(tensor)
                torch.cuda.synchronize();start=time.perf_counter()
                output=model.generate(input_ids=tensor,attention_mask=mask,max_new_tokens=64,do_sample=False,pad_token_id=tok.eos_token_id)
                torch.cuda.synchronize();seconds=time.perf_counter()-start
                answer=tok.decode(output[0,len(ids):].tolist(),skip_special_tokens=True).strip()
                row={'model_id':args.model_id,'family_id':family['family_id'],'item_id':item['id'],
                     'messages':messages,'prompt_token_ids':ids,'output':answer,'expected':item['output'],
                     'correct':answer==item['output'],'seconds':seconds,'pid':os.getpid(),
                     'cuda_allocated_bytes':torch.cuda.memory_allocated(),'cuda_reserved_bytes':torch.cuda.memory_reserved()}
                stream.write(json.dumps(row)+'\n');stream.flush();os.fsync(stream.fileno())
                del tensor,mask,output
            print(json.dumps({'family_id':family['family_id'],'complete':True}),flush=True)
    assert pins=={str(f.relative_to(args.model)):digest(f) for f in args.model.rglob('*') if f.is_file() and f.suffix in ('.safetensors','.json')}
    (args.out/'completion.json').write_text(json.dumps({'passed':True,'responses':480,'weights_unchanged':True,
         'end_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2)+'\n')

if __name__=='__main__':main()
