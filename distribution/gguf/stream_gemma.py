"""Private two-pass Gemma GGUF writer; buffers at most one encoded tensor.

Uses the pinned GGUF writer/quantizer, not a llama.cpp runtime or fork.
Canonical names follow the pinned vllm-gguf-plugin Gemma4 mapping.
"""
import argparse
import hashlib
import json
import math
import pathlib
import struct
import time

TEXT={
 'self_attn.q_norm.':'attn_q_norm.','self_attn.k_norm.':'attn_k_norm.',
 'self_attn.q_proj.':'attn_q.','self_attn.k_proj.':'attn_k.',
 'self_attn.v_proj.':'attn_v.','self_attn.o_proj.':'attn_output.',
 'input_layernorm.':'attn_norm.','post_attention_layernorm.':'post_attention_norm.',
 'pre_feedforward_layernorm_2.':'pre_ffw_norm_2.','pre_feedforward_layernorm.':'ffn_norm.',
 'post_feedforward_layernorm_1.':'post_ffw_norm_1.','post_feedforward_layernorm_2.':'post_ffw_norm_2.',
 'post_feedforward_layernorm.':'post_ffw_norm.',
 'mlp.gate_proj.':'ffn_gate.','mlp.up_proj.':'ffn_up.','mlp.down_proj.':'ffn_down.',
 'router.proj.':'ffn_gate_inp.', 'router.scale':'ffn_gate_inp.scale',
 'router.per_expert_scale':'ffn_down_exps.scale',
 'experts.gate_up_proj':'ffn_gate_up_exps.weight','experts.down_proj':'ffn_down_exps.weight',
 'layer_scalar':'layer_output_scale.weight'}
VISION={'self_attn.q_norm.':'attn_q_norm.','self_attn.k_norm.':'attn_k_norm.',
 'self_attn.q_proj.linear.':'attn_q.','self_attn.k_proj.linear.':'attn_k.',
 'self_attn.v_proj.linear.':'attn_v.','self_attn.o_proj.linear.':'attn_out.',
 'mlp.gate_proj.linear.':'ffn_gate.','mlp.up_proj.linear.':'ffn_up.','mlp.down_proj.linear.':'ffn_down.',
 'input_layernorm.':'ln1.','post_attention_layernorm.':'attn_post_norm.',
 'pre_feedforward_layernorm.':'ln2.','post_feedforward_layernorm.':'ffn_post_norm.'}


def name_for(name):
    direct={'model.language_model.embed_tokens.':'token_embd.',
        'model.language_model.norm.':'output_norm.','lm_head.':'output.',
        'model.vision_tower.patch_embedder.position_embedding_table':'v.position_embd.weight',
        'model.vision_tower.std_bias':'v.std_bias','model.vision_tower.std_scale':'v.std_scale',
        'model.vision_tower.patch_embedder.input_proj.':'v.patch_embd.',
        'model.embed_vision.embedding_projection':'mm.input_projection'}
    for old,new in direct.items():
        if name.startswith(old):return new+name[len(old):]
    for prefix,target,mapping in [('model.language_model.layers.','blk.',TEXT),('model.vision_tower.encoder.layers.','v.blk.',VISION)]:
        if name.startswith(prefix):
            layer,rest=name[len(prefix):].split('.',1)
            if not layer.isdigit():raise ValueError('invalid source layer')
            for old,new in mapping.items():
                if rest.startswith(old):return target+layer+'.'+new+rest[len(old):]
    raise ValueError('unmapped source tensor: '+name)


def plan(root):
    config=json.loads((root/'config.json').read_text())
    if config['model_type']!='gemma4':raise ValueError('this profile requires native gemma4 configuration')
    index=json.loads((root/'model.safetensors.index.json').read_text());rows=[];names=set()
    for shard in sorted(set(index['weight_map'].values())):
        if pathlib.Path(shard).name!=shard:raise ValueError('nonlocal shard')
        with (root/shard).open('rb') as f:
            length=struct.unpack('<Q',f.read(8))[0]
            if length>64*1024**2:raise ValueError('excessive checkpoint header')
            header=json.loads(f.read(length))
        for original,entry in header.items():
            if original=='__metadata__':continue
            if index['weight_map'].get(original)!=shard:raise ValueError('checkpoint index mismatch')
            name=name_for(original)
            if name in names:raise ValueError('duplicate output tensor')
            names.add(name);shape=entry['shape']
            q8=len(shape)>=2 and shape[-1]%32==0 and name.startswith(('blk.','token_embd.','output.')) and 'ffn_gate_inp.' not in name
            size=math.prod(shape)//32*34 if q8 else math.prod(shape)*4
            rows.append(dict(source=original,shard=shard,name=name,shape=shape,q8=q8,bytes=int(size)))
    if len(rows)!=len(index['weight_map']):raise ValueError('incomplete checkpoint')
    return rows


def encode_slice(weights,row,chunk_bytes=8*1024**2):
    import numpy as np
    import gguf
    shape=row['shape'];stored=list(shape)
    if row['q8']:stored[-1]=stored[-1]//32*34
    out=np.empty(stored,dtype=np.uint8 if row['q8'] else np.float32)
    step=max(1,chunk_bytes//max(1,math.prod(shape[1:])*4))
    view=weights.get_slice(row['source'])
    for start in range(0,shape[0],step):
        chunk=view[start:start+step].float().numpy()
        out[start:start+step]=gguf.quants.quantize(chunk,gguf.GGMLQuantizationType.Q8_0) if row['q8'] else chunk
    assert out.nbytes==row['bytes']
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--output');p.add_argument('--report',required=True);p.add_argument('--plan-only',action='store_true');a=p.parse_args()
    root=pathlib.Path(a.model);rows=plan(root)
    report={'status':'planned','scope':'Complete checkpoint conversion, no model accuracy/serving certification','tensor_count':len(rows),'q8_tensors':sum(r['q8'] for r in rows),'payload_bytes':sum(r['bytes'] for r in rows),'largest_encoded_tensor_bytes':max(r['bytes'] for r in rows),'config_sha256':hashlib.sha256((root/'config.json').read_bytes()).hexdigest(),'rows':rows}
    path=pathlib.Path(a.report);path.write_text(json.dumps(report,indent=2)+chr(10))
    if a.plan_only:return
    if not a.output:raise ValueError('output required')
    out=pathlib.Path(a.output)
    if out.exists():raise ValueError('preserve existing output')
    import gguf
    import numpy as np
    import torch
    from safetensors import safe_open
    torch.set_num_threads(2)
    writer=gguf.GGUFWriter(str(out),'gemma4',use_temp_file=False)
    writer.add_name('Gemma4 Q8_0 private validation');writer.add_file_type(gguf.LlamaFileType.MOSTLY_Q8_0)
    writer.add_string('aimee.hf_architecture','gemma4')
    for row in rows:
        writer.add_tensor_info(row['name'],row['shape'],np.dtype('float32'),row['bytes'],raw_dtype=gguf.GGMLQuantizationType.Q8_0 if row['q8'] else gguf.GGMLQuantizationType.F32)
    writer.write_header_to_file();writer.write_kv_data_to_file();writer.write_ti_data_to_file()
    started=time.monotonic();completed=0
    try:
        for shard in dict.fromkeys(r['shard'] for r in rows):
            with safe_open(root/shard,framework='pt',device='cpu') as weights:
                for row in rows:
                    if row['shard']!=shard:continue
                    tensor=encode_slice(weights,row);writer.write_tensor_data(tensor);del tensor
                    completed+=1
                    print(json.dumps({'tensors_written':completed,'total':len(rows)}),flush=True)
        writer.close()
        reader=gguf.GGUFReader(str(out))
        assert len(reader.tensors)==len(rows)
        for tensor,row in zip(reader.tensors,rows):
            assert tensor.name==row['name'] and tuple(reversed(tensor.shape))==tuple(row['shape'])
        with out.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        report.update(status='converted',sha256=digest,bytes=out.stat().st_size,seconds=time.monotonic()-started)
    except BaseException:
        report.update(status='failed',tensors_written=completed);raise
    finally:path.write_text(json.dumps(report,indent=2)+chr(10))


if __name__=='__main__':main()
