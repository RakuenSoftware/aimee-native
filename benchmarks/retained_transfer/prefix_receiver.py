"""Untrained HF complete-prefix reference for attention and hybrid receivers.

This is one-record ordered continuation, not independent-bank composition.
All active weights and cache tensors remain on CUDA. Forensic hash copies are
outside timed inference and never replace the active state.
"""
import copy,hashlib,json,time
from pathlib import Path


def state_leaves(name,value):
    # Modern hybrid caches index convolution/recurrent tensors by state ID.
    # Walk every populated state rather than assuming one tensor per layer.
    if value is None:return
    if isinstance(value,dict):
        for key in sorted(value,key=str):yield from state_leaves(name+'.'+str(key),value[key])
    elif isinstance(value,(list,tuple)):
        for index,child in enumerate(value):yield from state_leaves(name+'.'+str(index),child)
    else:yield name,value


def cache_tensors(cache):
    for index,layer in enumerate(cache.layers):
        for field in ('keys','values','conv_states','recurrent_states'):
            yield from state_leaves(str(index)+'.'+field,getattr(layer,field,None))


def state_identity(cache):
    import torch
    h=hashlib.sha256();geometry=[];size=0
    for name,tensor in cache_tensors(cache):
        assert tensor.device.type=='cuda'
        entry={'name':name,'shape':list(tensor.shape),'dtype':str(tensor.dtype)}
        raw=tensor.detach().contiguous().view(-1).view(torch.uint8).cpu().numpy().tobytes()
        h.update(json.dumps(entry,sort_keys=True).encode());h.update(raw)
        geometry.append(entry);size+=tensor.numel()*tensor.element_size()
    assert geometry,'No native cache tensors found'
    return {'sha256':h.hexdigest(),'geometry':geometry,'logical_bytes':size}


class PrefixReceiver:
    def __init__(self,path):
        import torch
        from transformers import AutoConfig,AutoTokenizer,AutoModelForCausalLM,AutoModelForImageTextToText
        self.torch=torch;self.tokenizer=AutoTokenizer.from_pretrained(path,local_files_only=True)
        config=AutoConfig.from_pretrained(path,local_files_only=True)
        klass=AutoModelForImageTextToText if config.model_type in ('gemma4','qwen3_5') else AutoModelForCausalLM
        self.model=klass.from_pretrained(path,local_files_only=True,dtype=torch.bfloat16,attn_implementation='sdpa').to('cuda').eval()
        self.model.requires_grad_(False)
        assert all(p.device.type=='cuda' and not p.requires_grad for p in self.model.parameters())
        self.versions=[(id(p),p._version) for p in self.model.parameters()]
        self.config=self.model.config.get_text_config()
        eos=self.model.generation_config.eos_token_id
        self.eos=set(eos if isinstance(eos,list) else [eos])
        self.prepared={}

    def full_tokens(self,messages):
        ids=self.tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)
        return ids if isinstance(ids,list) else ids['input_ids']

    def forward(self,ids,cache=None):
        torch=self.torch
        assert ids
        offset=cache.get_seq_length() if cache is not None else 0
        assert offset+len(ids)<=self.config.max_position_embeddings
        args={'input_ids':torch.tensor([ids],device='cuda'),'use_cache':True,'logits_to_keep':1,
              'attention_mask':torch.ones((1,offset+len(ids)),dtype=torch.long,device='cuda'),
              'position_ids':torch.arange(offset,offset+len(ids),device='cuda').unsqueeze(0)}
        if cache is not None:args['past_key_values']=cache
        return self.model(**args)

    def prepare(self,key,prefix_ids):
        assert key not in self.prepared and prefix_ids
        torch=self.torch;torch.cuda.synchronize();start=time.perf_counter()
        with torch.inference_mode():result=self.forward(prefix_ids)
        torch.cuda.synchronize();seconds=time.perf_counter()-start
        cache=result.past_key_values;del result
        identity=state_identity(cache)
        self.prepared[key]={'cache':cache,'prefix_ids':list(prefix_ids),'seconds':seconds,'state':identity}
        return {k:v for k,v in self.prepared[key].items() if k!='cache'}

    def answer(self,ids,key=None,cap=64):
        torch=self.torch;assert cap==64
        # Caller supplies independently audited exact execution IDs. Native
        # prefix + suffix must equal full Text IDs on the same acquired record.
        torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();start=time.perf_counter()
        prefix=0;state=None
        with torch.inference_mode():
            if key is not None:
                stored=self.prepared[key];state=copy.deepcopy(stored['cache']);prefix=len(stored['prefix_ids'])
                assert all(t.device.type=='cuda' for _,t in cache_tensors(state))
            torch.cuda.synchronize();attached=time.perf_counter()-start
            result=self.forward(ids,state);state=result.past_key_values
            output=[];first=None
            for step in range(cap):
                token=int(result.logits[0,-1].argmax());output.append(token)
                if first is None:
                    torch.cuda.synchronize();first=time.perf_counter()-start
                if token in self.eos:break
                if step+1<cap:
                    result=self.forward([token],state);state=result.past_key_values
            torch.cuda.synchronize();end=time.perf_counter()-start
            peak_allocated=torch.cuda.max_memory_allocated();peak_reserved=torch.cuda.max_memory_reserved()
        assert self.versions==[(id(p),p._version) for p in self.model.parameters()]
        answer=self.tokenizer.decode(output,skip_special_tokens=True).strip()
        del result,state
        return {'output':answer,'output_token_ids':output,'execution_token_ids':list(ids),
            'engine_ttft_ms':first*1000,'engine_end_ms':end*1000,'attachment_ms':attached*1000,
            'prefill_tokens':len(ids),'native_prefix_tokens':prefix,
            'peak_cuda_allocated_bytes':peak_allocated,'peak_cuda_reserved_bytes':peak_reserved,
            'all_active_cache_cuda':True,'weights_version_unchanged':True,
            'timing_scope':'Engine call including cache clone/attachment, tensor construction and decode; caller must add frontend/tokenization for request-level C5.'}

    def retire(self,key):
        value=self.prepared.pop(key)
        assert state_identity(value['cache'])==value['state'],'Prepared state mutated across requests'
        del value
