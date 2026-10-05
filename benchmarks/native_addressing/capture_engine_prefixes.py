"""Prepare complete native prefixes with the exact serving engine arithmetic."""
import argparse
import json
import os
import time
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True);p.add_argument('--requests',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();config=json.loads(Path(args.config).read_text());serve=config['serve']
    if config.get('offline_prefix_capture') is not True:raise ValueError('offline capture configuration required')
    output=Path(args.output);output.mkdir(mode=0o700)
    module=config.get('python_module','aimee_vllm')
    plugin=config.get('plugin',module if module!='aimee_vllm' else 'aimee_native')
    os.environ.update(AIMEE_VLLM_CONFIG=str(Path(args.config).resolve()),VLLM_PLUGINS=plugin,
                      VLLM_USE_V2_MODEL_RUNNER='0',VLLM_USE_FLASHINFER_SAMPLER='0')
    # Match the declared transfer policy, including a pinned-copy profile that
    # deliberately disables UVA reads. Do not inherit unrelated shell settings.
    os.environ['VLLM_WEIGHT_OFFLOADING_DISABLE_PIN_MEMORY']='0' if serve.get('cpu_offload_pinned_memory',True) else '1'
    os.environ['VLLM_WEIGHT_OFFLOADING_DISABLE_UVA']='1' if (serve.get('cpu_offload_disable_uva',False) or not serve.get('cpu_offload_pinned_memory',True)) else '0'
    from vllm import LLM,SamplingParams
    from tokenizers import Tokenizer
    load_started=time.perf_counter()
    llm=LLM(model=config['model'],dtype='bfloat16',quantization=config.get('quantization'),enforce_eager=True,
            enable_prefix_caching=False,async_scheduling=False,worker_cls=module+'.worker.AimeeWorker',
            attention_config={'backend':'CUSTOM'},limit_mm_per_prompt={'image':0,'audio':0,'video':0},
            mamba_ssm_cache_dtype='float32',additional_config={'gdn_prefill_backend':'triton'},
            cpu_offload_gb=serve['cpu_offload_gb'],cpu_offload_params=serve['cpu_offload_params'],
            max_model_len=serve['max_model_len'],max_num_seqs=1,max_num_batched_tokens=serve['max_num_batched_tokens'],
            gpu_memory_utilization=serve['gpu_memory_utilization'],num_gpu_blocks_override=serve.get('num_gpu_blocks_override'))
    load_seconds=time.perf_counter()-load_started
    preparation=[]
    tokenizer=Tokenizer.from_file(str(Path(config['model'])/'tokenizer.json'))
    requests=json.loads(Path(args.requests).read_text());publications={}
    for name,request in requests.items():
        text='<|im_start|>system\n'+request['context'].strip()+'\n\nAuthoritative memory:\n'+request['facts']+'<|im_end|>\n'
        tokens=tokenizer.encode(text,add_special_tokens=False).ids
        started=time.perf_counter()
        llm.llm_engine.collective_rpc('aimee_capture_begin',args=(tokens,request['context'],str(output/name)))
        llm.generate([{'prompt_token_ids':tokens}],SamplingParams(temperature=0,max_tokens=1),use_tqdm=False)
        result=llm.llm_engine.collective_rpc('aimee_capture_finish')
        if len(result)!=1:raise RuntimeError('capture rank coverage mismatch')
        elapsed=time.perf_counter()-started
        preparation.append({'publication':name,'tokens':len(tokens),'elapsed_seconds':elapsed})
        publications[name]=result[0]
        (output/'progress.json').write_text(json.dumps(publications,indent=2)+'\n')
        print(json.dumps({'captured':name,'tokens':len(tokens)}),flush=True)
    catalogue={'recipient':config['recipient'],'model_config_sha256':__import__('hashlib').sha256((Path(config['model'])/'config.json').read_bytes()).hexdigest(),'publications':publications}
    (output/'timing.json').write_text(json.dumps({'model_load_seconds':load_seconds,'scope':'offline capture plus CPU transfer and immutable publication; not routing or native attention consumption','preparation':preparation},indent=2)+'\n')
    (output/'catalog.json').write_text(json.dumps(catalogue,indent=2)+'\n')

if __name__=='__main__':main()
