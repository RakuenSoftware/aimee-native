"""Read local checkpoint topology and headers without loading weights or GPUs."""
import argparse
import collections
import hashlib
import json
import math
import pathlib
import struct


def inspect(root):
    root=pathlib.Path(root)
    config_bytes=(root/'config.json').read_bytes()
    config=json.loads(config_bytes)
    text=config.get('text_config',config)
    index_path=root/'model.safetensors.index.json'
    index=json.loads(index_path.read_text())
    shards=sorted(set(index['weight_map'].values()))
    sizes={};dtypes=collections.Counter();parameters=0;text_parameters=0
    tensors={}
    for name in shards:
        path=root/name
        if pathlib.Path(name).name!=name:raise ValueError('nonlocal checkpoint shard')
        sizes[name]=path.stat().st_size
        with path.open('rb') as stream:
            length=struct.unpack('<Q',stream.read(8))[0]
            if length>64*1024**2:raise ValueError('excessive checkpoint header')
            header=json.loads(stream.read(length))
        for tensor,entry in header.items():
            if tensor=='__metadata__':continue
            if index['weight_map'].get(tensor)!=name:raise ValueError('index/header mismatch')
            count=math.prod(entry['shape']);parameters+=count;dtypes[entry['dtype']]+=count
            if 'vision' not in tensor and 'audio' not in tensor:text_parameters+=count
            tensors[tensor]=entry
    if set(tensors)!=set(index['weight_map']):raise ValueError('incomplete indexed tensors')
    fields=('model_type','num_hidden_layers','hidden_size','head_dim','global_head_dim',
        'num_attention_heads','num_key_value_heads','num_global_key_value_heads',
        'num_kv_shared_layers','sliding_window','enable_moe_block','num_experts','top_k_experts')
    metadata=root/'.cache/huggingface/download/config.json.metadata'
    return dict(path=str(root),architectures=config.get('architectures'),model_type=config.get('model_type'),
        text_config={k:text[k] for k in fields if k in text},
        layer_types=dict(collections.Counter(text.get('layer_types',[]))),
        config_sha256=hashlib.sha256(config_bytes).hexdigest(),
        index_sha256=hashlib.sha256(index_path.read_bytes()).hexdigest(),
        download_revision=metadata.read_text().splitlines()[0] if metadata.exists() else None,
        shard_bytes=sizes,total_shard_bytes=sum(sizes.values()),tensor_elements=parameters,
        non_audio_vision_tensor_elements=text_parameters,dtype_elements=dict(dtypes),
        fp32_weight_bytes_estimate=4*parameters,license_files=[p.name for p in root.glob('*LICENSE*')],
        scope='Header/index completeness and sizes only. Weight payload hashes, runtime compatibility, memory fit and model accuracy remain unverified.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('paths',nargs='+');a=p.parse_args()
    print(json.dumps([inspect(path) for path in a.paths],indent=2))
