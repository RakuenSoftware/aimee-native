import os
import importlib,json,sys
from pathlib import Path
from types import SimpleNamespace
import torch
R=Path(os.environ.get('AIMEE_VALIDATION_ROOT', '/opt/aimee-plugin-validation-20261006'));checks=[]
def check(name,condition):checks.append(dict(name=name,passed=bool(condition)));assert condition,name
for model in [sys.argv[1]]:
 package='aimee_'+model.replace('-','_')
 Adapter=importlib.import_module(package+'.model_adapter').ModelAdapter
 Capture=importlib.import_module(package+'.small_model_capture').AttentionPrefixCapture
 adapter=Adapter({'adapter':model,'model':str(R/'models'/model)})
 obj=Capture.__new__(Capture);obj.adapter=adapter;obj.tokens=[1,2,3,4];obj.attention={}
 sources=adapter.description['kv_source_layers'];config=adapter.config['text_config']
 metadata=SimpleNamespace(query_start_loc=torch.tensor([0,2]))
 for chunk in range(2):
  for layer,source in enumerate(sources):
   if source==layer:
    heads=config['num_key_value_heads'];width=config['global_head_dim'] if config['layer_types'][layer]=='full_attention' else config['head_dim']
    key=torch.full((2,heads,width),layer+chunk,dtype=torch.bfloat16);value=key+1
   else:key=value=None
   obj.attention_chunk(layer,key,value,metadata)
  for layer,source in enumerate(sources):
   assert all(torch.equal(a,b) for a,b in zip(obj.attention[layer][0],obj.attention[source][0]))
 check(model+' shared K/V sources captured across two prefix chunks',all(len(parts[0])==2 for parts in obj.attention.values()))
 source_layer=next(i for i,s in enumerate(sources) if s!=i)
 for label,layer,key,value in [('partial tensors',source_layer,torch.zeros((2,1,256),dtype=torch.bfloat16),None),('nonshared missing tensors',0,None,None),('out of range layer',len(sources),None,None),('repeated source chunk',source_layer,None,None)]:
  try:obj.attention_chunk(layer,key,value,metadata);denied=False
  except RuntimeError:denied=True
  check(model+' rejects '+label,denied)
 result={'status':'passed','checks':checks,'scope':'Model-centric shared-K/V observation binding; CPU tensor structural tests, not GPU kernel execution'}
(R/'evidence'/(sys.argv[1]+'-fresh-capture.json')).write_text(json.dumps(result,indent=2)+'\n');print(str(len(checks))+' shared-K/V capture checks passed')
