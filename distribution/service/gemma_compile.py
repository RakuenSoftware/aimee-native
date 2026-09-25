"""Private CPU preparation worker; never distribute with the serving client."""
import argparse,json,sys
from pathlib import Path
import torch
from transformers import AutoTokenizer,Gemma4UnifiedForConditionalGeneration
p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--publisher-module',required=True);p.add_argument('--output',required=True);p.add_argument('--identity',required=True);p.add_argument('--key',required=True);a=p.parse_args()
sys.path.insert(0,a.publisher_module)
from native_loader import publish
request=json.load(sys.stdin)
facts=request['response']['facts'];records=request['identity']['records']
if not facts or len(facts)!=len(records):raise ValueError('incomplete selected working set')
# Aimee has already authorized this response. Consume all selected contents.
contents=[f['content'] for f in facts]
if not all(isinstance(s,str) and s for s in contents):raise ValueError('unsupported fact content')
torch.set_num_threads(12)
tokenizer=AutoTokenizer.from_pretrained(a.model,local_files_only=True)
model=Gemma4UnifiedForConditionalGeneration.from_pretrained(a.model,local_files_only=True,dtype=torch.bfloat16,device_map='cpu',attn_implementation='eager').eval()
text='Authoritative memory:\n'+'\n'.join(contents)
framed=tokenizer.apply_chat_template([{'role':'system','content':text}],tokenize=False,add_generation_prompt=False,enable_thinking=False)
tokens=tokenizer.encode(framed,add_special_tokens=False);ids=torch.tensor([tokens])
with torch.inference_mode():
 result=model(input_ids=ids,attention_mask=torch.ones_like(ids),position_ids=torch.arange(-len(tokens),0).unsqueeze(0),use_cache=True,logits_to_keep=1)
banks={i:(layer.keys.detach(),layer.values.detach()) for i,layer in enumerate(result.past_key_values.layers)}
publish(Path(a.output),a.identity,a.key,tokens,banks)
