import os
import hashlib,importlib,importlib.metadata,json,tempfile
from pathlib import Path
R=Path(os.environ.get('AIMEE_VALIDATION_ROOT', '/opt/aimee-plugin-validation-20261006'));checks=[]
def check(name,condition):
 checks.append(dict(name=name,passed=bool(condition)));assert condition,name
for model in ['gemma4-e2b','gemma4-e4b']:
 module='aimee_'+model.replace('-','_');adapter_class=importlib.import_module(module+'.model_adapter').ModelAdapter
 root=R/'models'/model;adapter=adapter_class({'model':str(root),'adapter':model})
 check(model+' own dedicated adapter admitted',adapter.description['adapter']==model)
 for other in ['gemma4-12b','gemma4-26b','qwen3-8-27b','gemma4-e2b','gemma4-e4b']:
  if other==model:continue
  try:adapter_class({'model':str(root),'adapter':other});denied=False
  except RuntimeError:denied=True
  check(model+' rejects foreign binding '+other,denied)
 with tempfile.TemporaryDirectory() as temp:
  target=Path(temp);(target/'tokenizer.json').write_bytes((root/'tokenizer.json').read_bytes());(target/'config.json').write_bytes((root/'config.json').read_bytes())
  versions={n:importlib.metadata.version(n) for n in ['torch','transformers']}
  profile={'adapter':model,'positioning':'native-prefix-absolute-v1','model_config_sha256':hashlib.sha256((target/'config.json').read_bytes()).hexdigest(),'tokenizer_sha256':hashlib.sha256((target/'tokenizer.json').read_bytes()).hexdigest(),'weights_sha256':'a'*64,'weight_profile':'stock-safetensors','versions':versions}
  def admit():return adapter.call('memory_profile',profile=profile,model_root=str(target),weights_sha256='a'*64,weight_profile='stock-safetensors',versions=versions)
  admit();check(model+' checkpoint publication identity accepted',True)
  (target/'tokenizer.json').write_bytes(b'changed tokenizer')
  try:admit();denied=False
  except RuntimeError:denied=True
  check(model+' changed tokenizer rejected',denied)
  (target/'tokenizer.json').write_bytes((root/'tokenizer.json').read_bytes());profile['weights_sha256']='b'*64
  try:admit();denied=False
  except RuntimeError:denied=True
  check(model+' different checkpoint rejected',denied)
 for contract in (Path(importlib.import_module(module).__file__).parent/'native').glob('adapter.json'):
  binding=json.loads(contract.read_bytes());library=contract.parent/'libaimee_native.so'
  check(model+' installed library matches binding digest',hashlib.sha256(library.read_bytes()).hexdigest()==binding['library_sha256'])
  import subprocess
  symbols=subprocess.check_output(['nm','-D',str(library)],text=True)
  present=[name for name in ['aimee_gemma4_12b_adapter','aimee_gemma4_26b_adapter','aimee_qwen3_8_27b_adapter','aimee_gemma4_e2b_adapter','aimee_gemma4_e4b_adapter'] if name in symbols]
  check(model+' ships exactly its dedicated Rust symbol',present==[module+'_adapter'])
result=dict(status='passed',checks=checks,shared_runtime_version=importlib.metadata.version('aimee-native-runtime'))
(R/'evidence/small-plugin-contracts.json').write_text(json.dumps(result,indent=2)+'\n');print(str(len(checks))+' installed plugin contract checks passed')
