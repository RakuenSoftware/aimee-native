"""Live full-model validation on unmodified vLLM plus the external plugin."""
import argparse
import json
import os
import time
p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',required=True);a=p.parse_args()
os.environ['AIMEE_VLLM_CONFIG']=a.config
os.environ['VLLM_USE_V2_MODEL_RUNNER']='0'
os.environ['VLLM_PLUGINS']='aimee_native'
os.environ['VLLM_ROCM_USE_AITER']='0'
from vllm import LLM,SamplingParams
config=json.load(open(a.config))
model=LLM(model=config['model'],tokenizer=config['model'],tensor_parallel_size=2,
          dtype='bfloat16',enforce_eager=True,enable_prefix_caching=False,
          max_model_len=2048,max_num_seqs=4,max_num_batched_tokens=256,
          gpu_memory_utilization=0.75,disable_custom_all_reduce=True,
          worker_cls='aimee_vllm.worker.AimeeWorker',
          attention_config={'backend':'CUSTOM'},async_scheduling=False,
          limit_mm_per_prompt={'image':0,'audio':0,'video':0})
tokenizer=model.get_tokenizer()
query='What is my private vault code? Reply with the code only.'
prompt=tokenizer.apply_chat_template([{'role':'user','content':query}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
conditions=[None,'alpha','beta','alpha']
params=[SamplingParams(temperature=0,max_tokens=24,extra_args={} if c is None else {'aimee_publication':c}) for c in conditions]
start=time.perf_counter();outputs=model.generate([prompt]*len(params),params,use_tqdm=False)
rows=[]
for cond,out in zip(conditions,outputs):
 rows.append({'condition':cond,'text':out.outputs[0].text,'prompt_tokens':len(out.prompt_token_ids),'output_tokens':len(out.outputs[0].token_ids)})
report={'rows':rows,'seconds':time.perf_counter()-start,'upstream_source_modified':False}
open(a.output,'w').write(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
assert len({r['prompt_tokens'] for r in rows})==1,'native memory changed prompt token count'
assert '68731' in rows[1]['text'] and '94268' in rows[2]['text'] and '68731' in rows[3]['text'],'native recall/isolation failed'
# Every independently selected record must remain available in the same answer.
query='Give my private vault code, private project codename, and preferred meeting drink. Be concise.'
prompt=tokenizer.apply_chat_template([{'role':'user','content':query}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
outputs=model.generate([prompt,prompt],[SamplingParams(temperature=0,max_tokens=80,extra_args={'aimee_publication':c}) for c in ['alpha','beta']],use_tqdm=False)
composition=[o.outputs[0].text for o in outputs]
report['composition']=composition
# Update an alias through a worker RPC; a new request must consume the new revision.
from pathlib import Path
catalog_path=Path(config['catalog']);original=catalog_path.read_text()
try:
 catalog=json.loads(original);catalog['publications']['alpha']=catalog['publications']['beta']
 staged=catalog_path.with_suffix('.next');staged.write_text(json.dumps(catalog));staged.replace(catalog_path)
 report['refresh']=model.collective_rpc('aimee_refresh_catalog')
 result=model.generate([prompt],SamplingParams(temperature=0,max_tokens=80,extra_args={'aimee_publication':'alpha'}),use_tqdm=False)[0]
 report['replacement']=result.outputs[0].text
finally:
 staged=catalog_path.with_suffix('.next');staged.write_text(original);staged.replace(catalog_path)
 model.collective_rpc('aimee_refresh_catalog')
open(a.output,'w').write(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
assert all(word in composition[0].lower() for word in ['68731','kestrel','rooibos']), 'alpha composition failed'
assert all(word in composition[1].lower() for word in ['94268','osprey','ginger']), 'beta composition failed'
assert all(word in report['replacement'].lower() for word in ['94268','osprey','ginger']), 'replacement failed'
