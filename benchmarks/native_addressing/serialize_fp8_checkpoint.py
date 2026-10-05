"""Stream a local checkpoint into FP8 per-tensor decoder weights.

Private deployment preparation, never a repository artifact. Small scalar scales
are stored alongside each HF projection; vLLM handles fused shard rescaling.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024**2),b''):h.update(chunk)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--destination',required=True);p.add_argument('--revision',required=True)
    a=p.parse_args();source=Path(a.source);destination=Path(a.destination)
    destination.mkdir(mode=0o700,parents=True)
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file
    if torch.cuda.get_device_name(0)!='NVIDIA GeForce RTX 5080':raise RuntimeError('RTX 5080 required')
    projections={'gate_proj','up_proj','down_proj','q_proj','k_proj','v_proj','o_proj',
                 'in_proj_qkv','in_proj_z','in_proj_a','in_proj_b','out_proj'}
    weights={};files=[];quantized=0
    for path in sorted(source.glob('*.safetensors')):
        output={}
        with safe_open(path,framework='pt',device='cpu') as tensors:
            for name in tensors.keys():
                tensor=tensors.get_tensor(name)
                if '.layers.' in name and name.endswith('.weight') and name.split('.')[-2] in projections:
                    if tensor.ndim!=2 or tensor.dtype!=torch.bfloat16:raise ValueError('unexpected projection geometry/dtype')
                    gpu=tensor.to('cuda');scale=(gpu.abs().max().float()/448).clamp_min(torch.finfo(torch.float32).tiny)
                    fp8=(gpu.float()/scale).clamp(-448,448).to(torch.float8_e4m3fn)
                    output[name]=fp8.cpu();output[name[:-6]+'weight_scale']=scale.reshape(1).cpu()
                    quantized+=1
                    del gpu,fp8,scale
                else:output[name]=tensor
                del tensor
        target=destination/path.name;save_file(output,str(target),metadata={'format':'pt'})
        files.append({'file':path.name,'source_sha256':digest(path),'sha256':digest(target),'bytes':target.stat().st_size})
        weights.update({name:path.name for name in output});del output
        print(json.dumps({'shard':path.name,'quantized_projections':quantized}),flush=True)
    manifest={'schema':1,'source_revision':a.revision,'algorithm':'fp8-e4m3fn-per-tensor-amax-divide-f32-v1',
              'activation_scheme':'dynamic','quantized_projections':quantized,'files':files}
    raw=(json.dumps(manifest,sort_keys=True)+'\n').encode();(destination/'weight-provenance.json').write_bytes(raw)
    config=json.loads((source/'config.json').read_text())
    config['quantization_config']={'quant_method':'fp8','activation_scheme':'dynamic'}
    config['aimee_weight_manifest_sha256']=hashlib.sha256(raw).hexdigest()
    for path in source.iterdir():
        if path.is_file() and path.suffix in ('.json','.jinja','.txt') and path.name not in ('config.json','model.safetensors.index.json'):
            shutil.copyfile(path,destination/path.name)
    (destination/'config.json').write_text(json.dumps(config,indent=2)+'\n')
    (destination/'model.safetensors.index.json').write_text(json.dumps({'metadata':{'total_size':sum(x['bytes'] for x in files)},'weight_map':weights},indent=2)+'\n')

if __name__=='__main__':main()
