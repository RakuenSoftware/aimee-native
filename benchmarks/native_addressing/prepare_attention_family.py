"""Independent attention-only family coverage with public synthetic facts.

The BF16 encoder and Q8 consumer are a measured external-memory profile; this
is not the matching-arithmetic complete hybrid prefix contract.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('model','output'):p.add_argument('--'+key,required=True)
    a=p.parse_args();root=Path(a.output);root.mkdir(mode=0o700)
    import torch
    from transformers import AutoTokenizer,Gemma4UnifiedForConditionalGeneration
    torch.set_num_threads(12)
    tokenizer=AutoTokenizer.from_pretrained(a.model,local_files_only=True)
    model=Gemma4UnifiedForConditionalGeneration.from_pretrained(a.model,local_files_only=True,dtype=torch.bfloat16,device_map='cpu',attn_implementation='eager').eval()
    facts=['The workshop vault entry number is 68731.','The workshop project codename is Kestrel.','The workshop preferred meeting drink is rooibos.']
    text=tokenizer.apply_chat_template([{'role':'system','content':'Authoritative memory:\n'+'\n'.join(facts)}],tokenize=False,add_generation_prompt=False,enable_thinking=False)
    tokens=tokenizer.encode(text,add_special_tokens=False);started=time.perf_counter()
    with torch.inference_mode():
        result=model(input_ids=torch.tensor([tokens]),attention_mask=torch.ones(1,len(tokens),dtype=torch.long),position_ids=torch.arange(-len(tokens),0).unsqueeze(0),use_cache=True,logits_to_keep=1)
    encoding_seconds=time.perf_counter()-started
    data=bytearray();segments=[]
    for layer,cache in enumerate(result.past_key_values.layers):
        for value,tensor in enumerate((cache.keys,cache.values)):
            if tensor.dtype!=torch.bfloat16 or tensor.shape[0]!=1 or tensor.shape[2]!=len(tokens):raise RuntimeError('attention family cache geometry mismatch')
            data.extend(tensor.cpu().contiguous().view(torch.uint8).numpy().tobytes())
            segments.append({'layer':layer,'value':bool(value),'heads':tensor.shape[1],'width':tensor.shape[3],'positions':len(tokens)})
    digest=lambda raw:hashlib.sha256(raw).hexdigest()
    identity='gemma4-12b-bf16-negativeprefix-public-20261004';key='workshop';offset=(4096+len(data)+4095)&~4095
    bank=root/'workshop';bank.mkdir(mode=0o700)
    (bank/'compact.pack').write_bytes(b'\0'*4096+data+b'\0'*(offset-4096-len(data))+b''.join(i.to_bytes(4,'little') for i in range(len(tokens))))
    index={'version':1,'model':identity,'schema':{'segments':segments,'row_bytes':sum(s['heads']*s['width']*2 for s in segments)},'prototypes':len(tokens),'dictionary_bytes':len(data),'dictionary_sha256':digest(data),'records':{key:{'offset':offset,'tokens':tokens}},'experimental_approximation':False,'head_major':False,'native_layout':True}
    (bank/'index.json').write_text(json.dumps(index,sort_keys=True)+'\n')
    catalogue={'recipient':'public-attention-family-canary','model_config_sha256':digest((Path(a.model)/'config.json').read_bytes()),'publications':{'workshop':{'root':str(bank),'model':identity,'key':key}}}
    (root/'catalog.json').write_text(json.dumps(catalogue,indent=2)+'\n')
    (root/'preparation.json').write_text(json.dumps({'scope':__doc__,'facts':facts,'tokens':tokens,'layers':len(result.past_key_values.layers),'dictionary_bytes':len(data),'encoding_seconds':encoding_seconds,'model_config_sha256':catalogue['model_config_sha256']},indent=2)+'\n')

if __name__=='__main__':main()
