"""CPU serving state. Owner-selected immutable banks; no semantic resolution."""
from dataclasses import dataclass
import hashlib,json,re
from collections import deque
from pathlib import Path
import torch
CURRENT=None
@dataclass(frozen=True)
class Bank:
    revision:str
    publication_sha256:str
    tokens:int
    layers:dict
    fingerprint:str
    bytes:int
@dataclass(frozen=True)
class Pin:
    bank:object
    capturing:bool=False
class CPUState:
    def __init__(self,config,runner):
        self.config=config;self.runner=runner;self.pins={};self.banks={};self.capture=None;self.shadow={}
        self.reads=0;self.observations=deque(maxlen=8192);self.current_revision=None
        raw=json.loads((Path(config['model'])/'config.json').read_bytes());text=raw.get('text_config',raw)
        if text['model_type'] not in ('gemma4_text','qwen3'):raise RuntimeError('CPU profile supports Gemma4 text and Qwen3 dense only')
        self.expected_layers=text['num_hidden_layers'];self.versions=None
    def begin(self,scheduler):
        for rid in scheduler.finished_req_ids:
            self.pins.pop(rid,None);self.shadow.pop(rid,None)
        for req in scheduler.scheduled_new_reqs:
            extra=req.sampling_params.extra_args or {};capture=self.capture
            if capture is not None:
                if extra.get('aimee_cpu_capture')!=capture['nonce']:raise RuntimeError('exclusive CPU capture nonce mismatch')
                if capture.get('internal_id') is None:capture['internal_id']=req.req_id
                elif capture['internal_id']!=req.req_id:raise RuntimeError('exclusive CPU capture request changed')
                pin=Pin(None,True)
            else:
                if extra.get('aimee_cpu_capture') is not None:raise RuntimeError('unarmed CPU capture')
                revision=extra.get('aimee_publication');bank=self.banks.get(revision)
                if revision is not None and bank is None:raise RuntimeError('CPU publication unavailable')
                if bank is not None and extra.get('aimee_catalog_digest')!=bank.fingerprint:raise RuntimeError('CPU frontend/worker bank mismatch')
                pin=Pin(bank)
            previous=self.pins.get(req.req_id)
            if previous is not None and previous!=pin:raise RuntimeError('CPU pinned request changed')
            self.pins[req.req_id]=pin
    def ids(self,common):
        slots=getattr(common,'req_idx',None);batch=self.runner.input_batch.req_ids
        ids=tuple(batch[:common.num_reqs]) if slots is None else tuple(batch[int(i)] for i in slots[:common.num_reqs])
        if len(ids)!=common.num_reqs or len(set(ids))!=len(ids) or any(r not in self.pins for r in ids):raise RuntimeError('CPU request/metadata mapping mismatch')
        return ids
    def shift(self,module,args,kwargs):
        from vllm.forward_context import get_forward_context
        metadata=get_forward_context().attn_metadata
        if not isinstance(metadata,dict):return args,kwargs
        entry=next((m for m in metadata.values() if getattr(m,'aimee_ids',None) is not None),None)
        if entry is None:return args,kwargs
        positions=kwargs.get('positions',args[1] if len(args)>1 else None)
        if positions is None or positions.dim()!=1:raise RuntimeError('CPU model positions unavailable')
        shifted=positions.clone();starts=entry.query_start_loc.tolist()
        for i,rid in enumerate(entry.aimee_ids):
            bank=self.pins[rid].bank
            if bank is not None:shifted[starts[i]:starts[i+1]]+=bank.tokens
        if 'positions' in kwargs:return args,{**kwargs,'positions':shifted}
        return (args[0],shifted,*args[2:]),kwargs
    def arm(self,request_id,nonce,tokens,revision,digest):
        if self.capture is not None or self.pins:raise RuntimeError('CPU capture requires a quiescent worker')
        if not 0<tokens<=1024 or not revision or len(digest)!=64:raise RuntimeError('invalid CPU capture')
        self.capture=dict(request_id=request_id,nonce=nonce,tokens=tokens,revision=revision,digest=digest,layers={})
        return {'state':'armed'}
    def finish(self):
        capture=self.capture;self.capture=None
        if capture is not None:
            rid=capture.get('internal_id',capture['request_id']);self.pins.pop(rid,None);self.shadow.pop(rid,None)
        if capture is None or len(capture['layers'])!=self.expected_layers:raise RuntimeError('incomplete CPU native capture')
        size=0;h=hashlib.sha256()
        for layer,(key,value) in sorted(capture['layers'].items()):
            if key.shape[-2]!=capture['tokens'] or value.shape[-2]!=capture['tokens']:raise RuntimeError('CPU capture token mismatch')
            for tensor in (key,value):
                if tensor.device.type!='cpu' or tensor.dtype!=torch.float32:raise RuntimeError('CPU capture profile mismatch')
                size+=tensor.numel()*tensor.element_size();h.update(tensor.contiguous().numpy().tobytes())
        if size>self.config.get('host_memory_budget',512*1024**2):raise RuntimeError('CPU native bank exceeds budget')
        bank=Bank(capture['revision'],capture['digest'],capture['tokens'],capture['layers'],h.hexdigest(),size)
        # Replace only unpinned storage after exclusive preparation. Owner chooses
        # this view; lexical order and semantic applicability are not considered.
        self.banks={bank.revision:bank};self.current_revision=bank.revision
        return dict(revision=bank.revision,publication_sha256=bank.publication_sha256,tokens=bank.tokens,layers=len(bank.layers),fingerprint=bank.fingerprint,bytes=bank.bytes,external_request_id=capture['request_id'],internal_request_id=capture.get('internal_id'))
    def audit(self):
        if self.versions is not None and self.versions!=[(id(p),p._version) for p in self.runner.model.parameters()]:raise RuntimeError('CPU model parameters changed')
        for bank in self.banks.values():
            h=hashlib.sha256()
            for _,pair in sorted(bank.layers.items()):
                for tensor in pair:h.update(tensor.contiguous().numpy().tobytes())
            if h.hexdigest()!=bank.fingerprint:raise RuntimeError('CPU native bank mutated')
        shadow_bytes=sum(t.numel()*t.element_size() for layers in self.shadow.values() for pair in layers.values() for t in pair)
        return dict(shadow_text_bytes=shadow_bytes,bank_fingerprints={r:b.fingerprint for r,b in self.banks.items()},device='cpu' ,native_attention_reads=self.reads,publications=len(self.banks),pinned_requests=len(self.pins),weights_unchanged=True,native_bytes=sum(b.bytes for b in self.banks.values()),observations=list(self.observations)[-128:])
