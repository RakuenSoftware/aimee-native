import os
import importlib,json,sys,torch
from pathlib import Path
model=sys.argv[1];module=importlib.import_module("aimee_"+model.replace("-","_")+".small_model_gguf")
name="model.language_model.layers.0.per_layer_input_gate.weight";kind=name+"_type";adapter=module.SmallGemmaWeightsAdapter();checks=[]
for label,weights in [("packed weight without type",[(name,torch.zeros((1,34),dtype=torch.uint8))]),("type without weight",[(kind,torch.tensor(8))]),("duplicate type",[(kind,torch.tensor(8)),(kind,torch.tensor(8))]),("unknown quantization type",[(kind,torch.tensor(999))])]:
 try:list(adapter.transform_weights(iter(weights),None));denied=False
 except (RuntimeError,ValueError):denied=True
 assert denied,label;checks.append(dict(name=label,passed=True))
weight=torch.ones((2,3),dtype=torch.bfloat16);result=list(adapter.transform_weights(iter([(name,weight)]),None));assert result[0][1] is weight
checks.append(dict(name="already floating projection preserved",passed=True))
other=torch.ones((2,3),dtype=torch.uint8);result=list(adapter.transform_weights(iter([("model.language_model.layers.0.self_attn.q_proj.weight",other)]),None));assert result[0][1] is other
checks.append(dict(name="other packed weights preserved",passed=True))
out=dict(status="passed",model=model,scope="Installed model projection conversion rejection tests; no GPU inference",checks=checks)
((Path(os.environ.get('AIMEE_VALIDATION_ROOT', '/opt/aimee-plugin-validation-20261006'))/'evidence')/(model+"-projection-rejections.json")).write_text(json.dumps(out,indent=2)+"\n")
print(model,len(checks),"projection conversion checks passed")
