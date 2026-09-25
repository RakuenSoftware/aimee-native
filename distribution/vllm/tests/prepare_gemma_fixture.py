"""Private, synthetic preparation fixture. Never installed with the client.
Uses the existing Rust publisher and an independent frozen-model pass on CPU;
serving contains no encoder. This is not an authorization/publication service.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import torch
from transformers import AutoTokenizer, Gemma4UnifiedForConditionalGeneration
p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--output',required=True);p.add_argument('--publisher-module',required=True);p.add_argument('--client-library',required=True);a=p.parse_args()
sys.path.insert(0,a.publisher_module)
from native_loader import publish
root=Path(a.output);root.mkdir(parents=True,exist_ok=False)
torch.set_num_threads(12)
tokenizer=AutoTokenizer.from_pretrained(a.model,local_files_only=True)
model=Gemma4UnifiedForConditionalGeneration.from_pretrained(a.model,local_files_only=True,dtype=torch.bfloat16,device_map='cpu',attn_implementation='eager').eval()
identity='gemma4-12b-bf16-negativeprefix-fixture-v1'
records={
 'alpha':['The user\'s private vault code is 68731.','The user\'s private project codename is Kestrel.','The user\'s preferred meeting drink is rooibos.'],
 'beta':['The user\'s private vault code is 94268.','The user\'s private project codename is Osprey.','The user\'s preferred meeting drink is ginger tea.'],
}
catalog={'model_config_sha256':hashlib.sha256((Path(a.model)/'config.json').read_bytes()).hexdigest(),'recipient':'synthetic-validation','publications':{}}
reports={}
for name,facts in records.items():
 text='Authoritative memory:\n'+'\n'.join(facts)
 framed=tokenizer.apply_chat_template([{'role':'system','content':text}],tokenize=False,add_generation_prompt=False,enable_thinking=False)
 tokens=tokenizer.encode(framed,add_special_tokens=False)
 ids=torch.tensor([tokens]);started=time.perf_counter()
 with torch.inference_mode():
  result=model(input_ids=ids,attention_mask=torch.ones_like(ids),position_ids=torch.arange(-len(tokens),0).unsqueeze(0),use_cache=True,logits_to_keep=1)
 banks={i:(layer.keys.detach(),layer.values.detach()) for i,layer in enumerate(result.past_key_values.layers)}
 path=root/name;publish(path,identity,name,tokens,banks)
 catalog['publications'][name]={'root':str(path),'model':identity,'key':name}
 reports[name]={'selected_records':facts,'encoder_tokens':len(tokens),'layers':len(banks),'seconds':time.perf_counter()-started}
 del result,banks
(root/'catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
config={'catalog':str(root/'catalog.json'),'model':a.model,'recipient':'synthetic-validation','library':a.client_library,'host_memory_budget':1024**3}
(root/'config.json').write_text(json.dumps(config,indent=2)+'\n')
(root/'preparation.json').write_text(json.dumps(reports,indent=2)+'\n')
print(json.dumps(reports),flush=True)
