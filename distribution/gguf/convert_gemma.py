"""Private format conversion using GGUF writer; no llama.cpp runtime or fork.
Original HF configuration/tokenizer accompany this text-serving weight artifact.
"""
import argparse,json,pathlib
import numpy as np
import torch
from safetensors import safe_open
import gguf
p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--output',required=True);a=p.parse_args()
root=pathlib.Path(a.model);config=json.loads((root/'config.json').read_text())
assert config['model_type']=='gemma4_unified'
# Match the upstream Gemma4 mapper, without importing its GPU extension here.
replacements={'self_attn.q_norm.':'attn_q_norm.','self_attn.k_norm.':'attn_k_norm.','self_attn.q_proj.':'attn_q.','self_attn.k_proj.':'attn_k.','self_attn.v_proj.':'attn_v.','self_attn.o_proj.':'attn_output.','input_layernorm.':'attn_norm.','post_attention_layernorm.':'post_attention_norm.','pre_feedforward_layernorm.':'ffn_norm.','post_feedforward_layernorm.':'post_ffw_norm.','mlp.gate_proj.':'ffn_gate.','mlp.up_proj.':'ffn_up.','mlp.down_proj.':'ffn_down.'}
def name_for(name):
 if name.startswith('model.language_model.layers.'):
  name='blk.'+name.removeprefix('model.language_model.layers.')
  if name.endswith('.layer_scalar'):return name.removesuffix('.layer_scalar')+'.layer_output_scale.weight'
  for source,target in replacements.items():name=name.replace(source,target)
 elif name.startswith('model.language_model.embed_tokens.'):name='token_embd.'+name.removeprefix('model.language_model.embed_tokens.')
 elif name.startswith('model.language_model.norm.'):name='output_norm.'+name.removeprefix('model.language_model.norm.')
 elif name.startswith('lm_head.'):name='output.'+name.removeprefix('lm_head.')
 return name
writer=gguf.GGUFWriter(a.output,'gemma4',use_temp_file=True)
writer.add_name('Gemma4Unified Q8_0 Aimee private validation')
writer.add_file_type(gguf.LlamaFileType.MOSTLY_Q8_0)
writer.add_string('aimee.hf_architecture','gemma4_unified')
count=quantized=0;seen=set();torch.set_num_threads(8)
for shard in sorted(root.glob('*.safetensors')):
 with safe_open(shard,framework='pt',device='cpu') as weights:
  for original in weights.keys():
   name=name_for(original)
   if name in seen:raise ValueError('duplicate mapped tensor')
   seen.add(name);tensor=weights.get_tensor(original).float().numpy()
   qt=gguf.GGMLQuantizationType.F32
   if tensor.ndim==2 and tensor.shape[-1]%32==0 and name.startswith(('blk.','token_embd.','output.')):
    qt=gguf.GGMLQuantizationType.Q8_0;tensor=gguf.quants.quantize(tensor,qt);quantized+=1
   writer.add_tensor(name,tensor,raw_dtype=qt);count+=1
   del tensor
writer.write_header_to_file();writer.write_kv_data_to_file();writer.write_tensors_to_file(progress=True);writer.close()
print(json.dumps({'tensors':count,'q8_tensors':quantized,'bytes':pathlib.Path(a.output).stat().st_size,'source_config':config['model_type']}),flush=True)
