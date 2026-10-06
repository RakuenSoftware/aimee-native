"""Lossless hybrid prefix admission and request-private GDN cache initialization.

No model execution or authority decisions occur here. The trusted catalogue binds
the complete prefix manifest to the same admitted attention publication.
"""
import hashlib
import json
from pathlib import Path
import torch


def validate_model_identity(spec, model_path, revision, runtime_config=None):
    """Bind derived states to the configured checkpoint, tokenizer and profile."""
    if (not isinstance(revision,str) or len(revision)<40
        or any(c not in '0123456789abcdef' for c in revision)):
        raise RuntimeError('hybrid serving requires an immutable model revision')
    root=Path(model_path)
    config=(root/'config.json').read_bytes()
    tokenizer=(root/'tokenizer.json').read_bytes()
    from .precision import runtime_profile,model_identity,encoder_weight_profile
    profile=runtime_profile(runtime_config or {})
    if profile and profile['quantization']=='fp8':
        quantized=json.loads(config).get('quantization_config',{})
        if (quantized.get('quant_method')!='fp8' or quantized.get('activation_scheme')!='dynamic'
            or quantized.get('weight_block_size') is not None):
            raise RuntimeError('unsupported hybrid FP8 checkpoint arithmetic')
    if profile and profile['quantization']=='gguf' and json.loads(config).get('quantization_config'):
        raise RuntimeError('GGUF capture requires an unquantized HF configuration')
    expected=model_identity(config,tokenizer,revision,profile)
    if spec.get('runtime_profile')!=profile:
        raise RuntimeError('hybrid serving arithmetic profile mismatch')
    if (spec.get('model_revision')!=revision or spec['model']!=expected
        or spec.get('tokenizer_sha256')!=hashlib.sha256(tokenizer).hexdigest()
        or spec['model_config_sha256']!=hashlib.sha256(config).hexdigest()
        or spec['encoder_weight_profile']!=encoder_weight_profile(profile)):
        raise RuntimeError('hybrid checkpoint/revision/tokenizer mismatch')


class HybridPrefix:
    def __init__(self, root, digest, model, key, limit=256*1024**2):
        root = Path(root)
        raw = (root/'hybrid.json').read_bytes()
        if len(raw)>4*1024**2 or hashlib.sha256(raw).hexdigest()!=digest:
            raise RuntimeError('hybrid manifest identity mismatch')
        spec = json.loads(raw)
        attention = (root/'index.json').read_bytes()
        if (spec['schema']!=1 or spec['model']!=model or spec['key']!=key
            or spec.get('positioning')!='native-prefix-absolute-v1'
            or spec['attention_index_sha256']!=hashlib.sha256(attention).hexdigest()):
            raise RuntimeError('hybrid/attention publication mismatch')
        self.spec = spec
        self.architecture = spec['architecture']
        m = spec['recurrent']
        if type(m['bytes']) is not int or not 0<m['bytes']<=limit or m['version']!=1:
            raise RuntimeError('hybrid recurrent byte budget exceeded')
        digest = m['sha256']
        if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise RuntimeError('invalid recurrent payload identity')
        if m.get('payload')!=digest+'.rnn.bin':
            raise RuntimeError('invalid recurrent payload path')
        path = root/m['payload']
        if path.stat().st_size!=m['bytes']:
            raise RuntimeError('hybrid payload size mismatch')
        self.data = bytearray(path.read_bytes())
        if hashlib.sha256(self.data).hexdigest()!=digest:
            raise RuntimeError('hybrid payload checksum mismatch')
        c = self.architecture
        q = c['linear_num_key_heads']*c['linear_key_head_dim']
        v = c['linear_num_value_heads']*c['linear_value_head_dim']
        shapes = {'conv':[1,2*q+v,c['linear_conv_kernel_dim']],
                  'recurrent':[1,c['linear_num_value_heads'],c['linear_key_head_dim'],c['linear_value_head_dim']]}
        layers = {i for i,k in enumerate(c['layer_types']) if k=='linear_attention'}
        parts = {};end=0
        for layout in m['layouts']:
            layer,part = layout['layer'],layout['part']
            dtype = {'bf16':torch.bfloat16,'f32':torch.float32}.get(layout['dtype'])
            shape = layout['shape']
            identity = (layer,part)
            if (layer not in layers or part not in shapes or identity in parts
                or shape!=shapes[part] or dtype is None
                or (part=='recurrent' and dtype!=torch.float32)
                or layout['offset']!=end):
                raise RuntimeError('hybrid state geometry/dtype mismatch')
            n=1
            for dimension in shape:n*=dimension
            size=n*torch.empty((),dtype=dtype).element_size()
            if size!=layout['bytes'] or end+size>len(self.data):
                raise RuntimeError('hybrid state extent mismatch')
            parts[identity]=torch.frombuffer(self.data,dtype=dtype,count=n,offset=end).reshape(shape)
            end+=size
        if end!=len(self.data) or set(parts)!={(i,p) for i in layers for p in shapes}:
            raise RuntimeError('incomplete hybrid state')
        self.parts=parts;self.plans={};self.devices={}

    def partition(self, rank, world):
        if (rank,world) in self.plans:return self.plans[rank,world]
        c=self.architecture
        if not 0<=rank<world or any(c[k]%world for k in ('linear_num_key_heads','linear_num_value_heads')):
            raise RuntimeError('hybrid tensor partition mismatch')
        q=c['linear_num_key_heads']*c['linear_key_head_dim']
        v=c['linear_num_value_heads']*c['linear_value_head_dim']
        result={}
        for layer,part in self.parts:
            if part!='conv':continue
            conv=self.parts[layer,'conv'][0]
            # Q/K/V are separate contiguous head groups. Each TP rank needs its
            # slice of all three, not one slice of the combined channel axis.
            conv=torch.cat([x.narrow(0,rank*(x.shape[0]//world),x.shape[0]//world)
                            for x in conv.split([q,q,v],dim=0)],dim=0)[:,-(c['linear_conv_kernel_dim']-1):].contiguous()
            recurrent=self.parts[layer,'recurrent'][0]
            recurrent=recurrent.narrow(0,rank*(recurrent.shape[0]//world),recurrent.shape[0]//world).transpose(-1,-2).contiguous()
            result[layer]=(conv,recurrent)
        self.plans[rank,world]=result
        return result

    def device_bytes(self, rank, world):
        return sum(t.numel()*t.element_size() for pair in self.partition(rank,world).values() for t in pair)

    def activate(self, device, rank, world):
        key=(str(device),rank,world)
        if key not in self.devices:
            self.devices[key]={i:tuple(t.to(device) for t in pair) for i,pair in self.partition(rank,world).items()}
        return self.devices[key]

    def evict(self, device, rank, world):
        self.devices.pop((str(device),rank,world),None)


def seed_layer(module, layer, runner, requests, rank, world, metadata, dim_first, adapter=None):
    """Called by a standard module pre-hook, with upstream request metadata.

    Initialization uses the real request's physical cache slot. Decode and later
    prefill chunks keep their evolving private state; zero-token recomputation
    after preemption deliberately reinitializes the prefix.
    """
    if metadata is None:return 0
    indices=metadata.non_spec_state_indices_tensor
    if indices is None or metadata.spec_sequence_masks is not None:
        raise RuntimeError('unsupported hybrid request metadata')
    count=indices.shape[0]
    ids=runner.input_batch.req_ids[:count]
    if len(ids)!=count or len(set(ids))!=len(ids):
        raise RuntimeError('hybrid request mapping mismatch')
    if adapter is None:
        raise RuntimeError('Qwen seeding requires its dedicated Rust adapter')
    observations=[]
    for j,rid in enumerate(ids):
        pin=requests.get(rid)
        if pin is None:raise RuntimeError('hybrid request is not pinned')
        observations.append((getattr(pin.store,'hybrid',None) is not None,
                             int(runner.input_batch.num_computed_tokens_cpu[j]),0))
    if not adapter.call('seed_needed',requests=observations):return 0
    # Decode and ordinary text requests do not need physical slot values.
    # Avoid a GPU -> CPU synchronization at every recurrent layer/token.
    slots=indices.tolist()
    rows=[(getattr(requests[rid].store,'hybrid',None) is not None,
           int(runner.input_batch.num_computed_tokens_cpu[j]),slot)
          for j,(rid,slot) in enumerate(zip(ids,slots))]
    initial=adapter.call('seed_plan',requests=rows,capacity=module.kv_cache[0].shape[0])
    for j in initial:
        rid,slot=ids[j],slots[j]
        pin=requests.get(rid)
        if pin is None:raise RuntimeError('hybrid request is not pinned')
        store=pin.store
        hybrid=getattr(store,'hybrid',None)
        if hybrid is None or int(runner.input_batch.num_computed_tokens_cpu[j])!=0:continue
        conv,recurrent=hybrid.devices[(str(module.kv_cache[0].device),rank,world)][layer]
        destination=module.kv_cache[0][slot]
        if not dim_first:conv=conv.transpose(-1,-2)
        target=module.kv_cache[1][slot]
        if destination.shape!=conv.shape or destination.dtype!=conv.dtype or target.shape!=recurrent.shape or target.dtype!=torch.float32:
            raise RuntimeError('hybrid runtime cache geometry/dtype mismatch')
        destination.copy_(conv);target.copy_(recurrent)
    if initial:
        if metadata.has_initial_state is None:raise RuntimeError('missing hybrid prefill initialization metadata')
        flags=metadata.has_initial_state.clone()
        flags[initial]=True
        metadata.has_initial_state=flags
        if metadata.prefill_has_initial_state is not None:
            metadata.prefill_has_initial_state=flags[metadata.num_decodes:]
    return len(initial)
