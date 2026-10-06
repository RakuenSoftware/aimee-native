import json,os,hashlib
from pathlib import Path
import torch
from transformers import AutoTokenizer
from aimee_native_runtime.composition import prepare_contract
ROOT=Path('/opt/jmlr-second-review-20261005/repair-cache/gemma-composition-candidate-r1')
NAS=Path('/mnt/pve/backup/aimee-experiments/root-evacuation-20261005-r1/gemma-composition-candidate-r1/gpu-validation-recovery-r4')
p=json.loads((NAS/'protocol.json').read_bytes());tokenizer=AutoTokenizer.from_pretrained(p['model']['model'],local_files_only=True)
proofs=[]
for c in json.loads((NAS/'cases.json').read_bytes()):
 text,bank,contract=prepare_contract(tokenizer,p['model']['model'],p['instruction'],[c['context']])
 native=[{'role':'system','content':p['instruction']},{'role':'user','content':c['question']}]
 full=[{'role':'system','content':p['instruction']+'\n\nAuthoritative memory:\n'+c['context']},{'role':'user','content':c['question']}]
 incoming=tokenizer.apply_chat_template(native,tokenize=True,add_generation_prompt=True,enable_thinking=False)['input_ids']
 text_ids=tokenizer.apply_chat_template(full,tokenize=True,add_generation_prompt=True,enable_thinking=False)['input_ids']
 prefix=contract['request_prefix_tokens'];assert incoming[:len(prefix)]==prefix
 suffix=incoming[len(prefix):];assert bank+suffix==text_ids and len(bank)<=1024 and len(text_ids)+p['decoding']['max_tokens']<=2048
 proofs.append({'id':c['id'],'bank_tokens':len(bank),'request_prefix_tokens':len(prefix),'task_suffix_tokens':len(suffix),'exact_composition':True,'bank_sha256':hashlib.sha256(json.dumps(bank,separators=(',',':')).encode()).hexdigest()})
assert not torch.cuda.is_initialized()
print(json.dumps({'status':'passed','scope':'actual installed stock tokenizer, compiled candidate preparation, six frozen inputs only; no inference','cuda_initialized':False,'cases':proofs},indent=2))
