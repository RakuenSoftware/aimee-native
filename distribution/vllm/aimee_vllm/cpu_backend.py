"""FP32 CPU serving bridge for the established separate native K/V mechanism.

Upstream CPU cache updates and profiling stay upstream. This bounded research
profile uses eager Torch attention when a request has an owner-selected bank.
"""
import re
import torch
from vllm.v1.attention.backends.cpu_attn import CPUAttentionBackend,CPUAttentionBackendImpl,CPUAttentionMetadataBuilder
from vllm.v1.attention.backend import AttentionType
from . import cpu_state as state
class AimeeCPUBuilder(CPUAttentionMetadataBuilder):
    def build(self,common_prefix_len,common_attn_metadata,fast_build=False):
        result=super().build(common_prefix_len,common_attn_metadata,fast_build)
        current=state.CURRENT
        result.aimee_ids=None if current is None or not current.pins else current.ids(common_attn_metadata)
        return result
class AimeeCPUBackend(CPUAttentionBackend):
    supported_dtypes=[torch.float32]
    supported_kv_cache_dtypes=['auto']
    @staticmethod
    def get_name():return 'CUSTOM'
    @staticmethod
    def get_impl_cls():return AimeeCPUImpl
    @staticmethod
    def get_builder_cls():return AimeeCPUBuilder
class AimeeCPUImpl(CPUAttentionBackendImpl):
    def forward(self,layer,query,key,value,kv_cache,attn_metadata,output,output_scale=None,output_block_scale=None):
        ids=getattr(attn_metadata,'aimee_ids',None)
        if ids is None:return super().forward(layer,query,key,value,kv_cache,attn_metadata,output,output_scale,output_block_scale)
        current=state.CURRENT
        match=re.search(r'(?:^|\.)layers\.(\d+)\.',layer.layer_name)
        if match is None:raise RuntimeError('CPU native layer identity unavailable')
        idx=int(match.group(1));heads=self.num_kv_heads
        starts=attn_metadata.query_start_loc.tolist()
        if current.capture is not None:
            if len(ids)!=1 or not current.pins[ids[0]].capturing:raise RuntimeError('CPU native capture is not exclusive')
            k,v=self._raw(current,ids[0],idx)
            k=k.unsqueeze(0).clone();v=v.unsqueeze(0).clone()
            current.capture['layers'][idx]=(k,v)
            return super().forward(layer,query,key,value,kv_cache,attn_metadata,output,output_scale,output_block_scale)
        if all(current.pins[r].bank is None for r in ids):return super().forward(layer,query,key,value,kv_cache,attn_metadata,output,output_scale,output_block_scale)
        if self.attn_type!=AttentionType.DECODER or self.alibi_slopes is not None or self.sinks is not None or output_scale is not None or output_block_scale is not None or attn_metadata.dynamic_causal is not None or not attn_metadata.causal:raise RuntimeError('unsupported CPU native attention')
        if query.device.type!='cpu' or query.dtype!=torch.float32 or kv_cache.dtype!=torch.float32:raise RuntimeError('CPU native requires FP32 CPU tensors')
        super().forward(layer,query,key,value,kv_cache,attn_metadata,output,output_scale,output_block_scale)
        q=query.view(-1,self.num_heads,self.head_size);out=output.view(-1,self.num_heads,self.head_size)
        for i,rid in enumerate(ids):
            bank=current.pins[rid].bank
            if bank is None:continue
            length=int(attn_metadata.seq_lens[i]);lo,hi=starts[i:i+2]
            tk,tv=self._raw(current,rid,idx)
            if tk.shape[1]!=length:raise RuntimeError('CPU raw text/cache length mismatch')
            prefix=0
            if bank is not None:
                mk,mv=bank.layers[idx];tk=torch.cat((mk[0],tk),1);tv=torch.cat((mv[0],tv),1);prefix=bank.tokens;current.reads+=1
            repeat=self.num_heads//self.num_kv_heads
            tk=tk.repeat_interleave(repeat,0);tv=tv.repeat_interleave(repeat,0)
            logits=torch.matmul(q[lo:hi].transpose(0,1),tk.transpose(-2,-1))*self.scale
            if self.logits_soft_cap:logits=self.logits_soft_cap*torch.tanh(logits/self.logits_soft_cap)
            queries=torch.arange(length-(hi-lo),length).unsqueeze(-1);keys=torch.arange(length).unsqueeze(0)
            allowed=keys<=queries
            if self.sliding_window!=-1:allowed&=keys>queries-self.sliding_window
            logits[:,:,prefix:].masked_fill_(~allowed.unsqueeze(0),float('-inf'))
            out[lo:hi]=torch.matmul(torch.softmax(logits,dim=-1),tv).transpose(0,1)
            if idx==0:current.observations.append(dict(request_id=rid,ordinary_seq_len=length,native_tokens=prefix,bank_fingerprint=None if bank is None else bank.fingerprint))
        return output

    def _raw(self,current,rid,idx):
        if self.kv_sharing_target_layer_name is not None:
            match=re.search(r'(?:^|\.)layers\.(\d+)\.',self.kv_sharing_target_layer_name)
            if match is None:raise RuntimeError('CPU shared K/V layer identity unavailable')
            idx=int(match.group(1))
        pair=current.shadow.get(rid,{}).get(idx)
        if pair is None:raise RuntimeError('CPU raw text K/V unavailable')
        return pair
    def do_kv_cache_update(self,layer,key,value,kv_cache,slot_mapping):
        super().do_kv_cache_update(layer,key,value,kv_cache,slot_mapping)
        from vllm.forward_context import get_forward_context
        metadata=get_forward_context().attn_metadata
        entry=metadata.get(layer.layer_name) if isinstance(metadata,dict) else None
        ids=getattr(entry,'aimee_ids',None)
        if ids is None:return
        current=state.CURRENT;match=re.search(r'(?:^|\.)layers\.(\d+)\.',layer.layer_name)
        if match is None:raise RuntimeError('CPU cache-update layer identity unavailable')
        idx=int(match.group(1));starts=entry.query_start_loc.tolist()
        k=key.view(-1,self.num_kv_heads,self.head_size);v=value.view(-1,self.num_kv_heads,self.head_size)
        for i,rid in enumerate(ids):
            pin=current.pins[rid]
            if pin.bank is None and not pin.capturing:continue
            lo,hi=starts[i:i+2];length=int(entry.seq_lens[i]);layers=current.shadow.setdefault(rid,{})
            old=layers.get(idx);previous=0 if old is None else old[0].shape[1]
            if previous!=length-(hi-lo):raise RuntimeError('CPU raw K/V continuation mismatch')
            nk=k[lo:hi].transpose(0,1).detach().clone();nv=v[lo:hi].transpose(0,1).detach().clone()
            layers[idx]=(nk,nv) if old is None else (torch.cat((old[0],nk),1),torch.cat((old[1],nv),1))
