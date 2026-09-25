"""Real GPU eviction/reload with room for only one of two memory banks."""
import argparse
import ctypes
import json
import os
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',required=True);a=p.parse_args()
from aimee_vllm.store import PreparedStore
config=json.loads(Path(a.config).read_text());catalog=json.loads(Path(config['catalog']).read_text())
sizes=[]
for spec in catalog['publications'].values():
 store=PreparedStore(ctypes.CDLL(config['library']),{**spec,'byte_budget':config['host_memory_budget'],'disk_backed':config.get('disk_backed',False)})
 sizes.append(store.device_bytes(2));store.close()
config['device_memory_budget']=max(sizes)
path=Path(a.output).with_suffix('.config.json');path.write_text(json.dumps(config))
os.environ.update(AIMEE_VLLM_CONFIG=str(path),VLLM_USE_V2_MODEL_RUNNER='0',VLLM_PLUGINS='aimee_native',VLLM_ROCM_USE_AITER='0')
from vllm import LLM,SamplingParams
model=LLM(model=config['model'],tokenizer=config['model'],tensor_parallel_size=2,dtype='bfloat16',enforce_eager=True,enable_prefix_caching=False,max_model_len=2048,max_num_seqs=4,max_num_batched_tokens=256,gpu_memory_utilization=.75,disable_custom_all_reduce=True,worker_cls='aimee_vllm.worker.AimeeWorker',attention_config={'backend':'CUSTOM'},async_scheduling=False,limit_mm_per_prompt={'image':0,'audio':0,'video':0})
prompt=model.get_tokenizer().apply_chat_template([{'role':'user','content':'What is my private vault code? Reply with the code only.'}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
rows=[]
for publication,expected in [('alpha','68731'),('beta','94268'),('alpha','68731')]:
 out=model.generate([prompt],SamplingParams(temperature=0,max_tokens=24,extra_args={'aimee_publication':publication}),use_tqdm=False)[0]
 rows.append({'publication':publication,'expected':expected,'text':out.outputs[0].text,'prompt_tokens':len(out.prompt_token_ids),'cache':model.collective_rpc('aimee_cache_stats')})
report={'budget_per_rank':config['device_memory_budget'],'bank_bytes_per_rank':sizes,'rows':rows}
Path(a.output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
assert all(row['expected'] in row['text'] for row in rows)
assert all(row['prompt_tokens']==26 for row in rows)
assert all(s['uploads']==3 and s['evictions']==2 and s['peak_bytes']<=config['device_memory_budget'] for s in rows[-1]['cache'])

if config.get('disk_backed',False):
 assert all(s['catalogue_payload_bytes']>config['host_memory_budget'] and s['mapped_payload_rss_bytes']==0 for row in rows for s in row['cache'])
