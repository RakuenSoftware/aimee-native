"""Persistent frozen Gemma worker using the existing Aimee native-memory code."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'integrations/qwen_aimee'))
import torch
import accelerate.hooks
from accelerate.utils.operations import send_to_device as original_send

def host_staged_send(value, device, non_blocking=False, skip_keys=None):
    # The dual-7900-XTX runtime already stages inter-device transfers via RAM.
    if isinstance(value, torch.Tensor):
        target=torch.device('cuda',device) if isinstance(device,int) else torch.device(device)
        if value.device.type=='cuda' and target.type=='cuda' and value.device!=target:
            return value.cpu().to(target,non_blocking=False)
        return original_send(value,device,non_blocking=non_blocking,skip_keys=skip_keys)
    if isinstance(value,(tuple,list)):
        return type(value)(host_staged_send(v,device,non_blocking,skip_keys) for v in value)
    if isinstance(value,dict):
        return type(value)({k:v if skip_keys and k in skip_keys else host_staged_send(v,device,non_blocking,skip_keys) for k,v in value.items()})
    return value
accelerate.hooks.send_to_device=host_staged_send
from transformers import AutoTokenizer, Gemma4UnifiedForConditionalGeneration
from local_image import AimeeImageClient
from qwen_adapter import QwenAimeeAdapter

class PublishedClient(AimeeImageClient):
    def __init__(self,reader,image):
        self.process=subprocess.Popen([str(reader),'serve-published','--root',str(image)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)
        self.timeout=30
        self.view=None
        self.authorization_id=None
    def search(self,query,limit):
        result=self.recall(query,limit,'test')
        if result['outcome']!='hit':raise RuntimeError('published fact not selected')
        return result['response']

p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--image',required=True);a=p.parse_args()
torch.set_num_threads(8)
tokenizer=AutoTokenizer.from_pretrained(a.model,local_files_only=True)
model=Gemma4UnifiedForConditionalGeneration.from_pretrained(a.model,local_files_only=True,dtype=torch.bfloat16,device_map='balanced',max_memory={0:'20GiB',1:'20GiB','cpu':'40GiB'},attn_implementation='eager').eval()
model.requires_grad_(False)
versions={name:p._version for name,p in model.named_parameters()}
client=PublishedClient(REPO/'.local/bin/aimee-memory-image',a.image)
device=model.get_input_embeddings().weight.device
adapter=QwenAimeeAdapter(model,tokenizer,client,input_device=device,host_memory=True)
print(json.dumps({'ready':True,'model':'google/gemma-4-12B-it','device_map':model.hf_device_map,'trainable_parameters':sum(p.numel() for p in model.parameters() if p.requires_grad)}),flush=True)
for line in sys.stdin:
    command=json.loads(line)
    query=command['query']
    messages=[{'role':'user','content':query}]
    ids=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False,return_tensors='pt',return_dict=True)['input_ids'].to(device)
    prompt=ids[0].cpu().tolist()
    started=time.perf_counter()
    row={'case':command['case'],'enabled':command['enabled'],'prompt_token_ids':prompt,'memory_prompt_tokens':0}
    try:
        state=None
        with torch.inference_mode():
            if command['enabled']:
                with adapter.request(query,recall_mode='prefill',reuse_encoding=command.get('reuse_encoding',False)) as state:
                    output=model.generate(input_ids=ids,attention_mask=torch.ones_like(ids),max_new_tokens=int(command.get("max_new_tokens",32)),do_sample=False,return_dict_in_generate=True,use_cache=True)
            else:
                output=model.generate(input_ids=ids,attention_mask=torch.ones_like(ids),max_new_tokens=int(command.get("max_new_tokens",32)),do_sample=False,return_dict_in_generate=True,use_cache=True)
        generated=output.sequences[0,len(prompt):].cpu().tolist()
        row.update(answer=tokenizer.decode(generated,skip_special_tokens=True).strip(),generated_ids=generated,main_cache_length=output.past_key_values.get_seq_length(),expected_main_cache_length=len(prompt)+len(generated)-1)
        if state is not None:
            row['memory']=state
            if command['case']=='initial':
                # Numerical integration check only; not a native-memory result.
                ref_ids=torch.tensor([state['memory_token_ids']+prompt],device=device)
                with torch.inference_mode():
                    ref=model(input_ids=ref_ids,attention_mask=torch.ones_like(ref_ids),use_cache=True,logits_to_keep=1)
                top=ref.logits[0,-1].float().topk(5).indices.cpu().tolist()
                row['integration_reference']={'explicit_prefix_top5_ids':top,'explicit_prefix_top5_tokens':[tokenizer.decode([x]) for x in top],'native_first_id':generated[0]}

        row['parameter_versions_unchanged']=all(p._version==versions[n] for n,p in model.named_parameters())
        assert row['parameter_versions_unchanged']
        assert row['main_cache_length']==row['expected_main_cache_length']
    except Exception as exc:
        import traceback
        traceback.print_exc(file=sys.stderr)
        row['error']=type(exc).__name__+': '+str(exc)
    row['seconds']=time.perf_counter()-started
    print(json.dumps(row),flush=True)
adapter.close();client.close()
