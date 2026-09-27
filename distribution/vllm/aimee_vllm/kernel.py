"""Fused attention over paged text and separately owned prepared memory.

Standard online softmax; no text reconstruction, encoder or mutation of vLLM's
text-cache slot map. This implementation is private and performance-gated.
"""
import triton
import triton.language as tl

@triton.jit
def native_attention(Q, CACHE, OUT, START, SEQLEN, BLOCKS, KP, VP, MLEN,
                     q_stride:tl.constexpr, q_head_stride:tl.constexpr,
                     c_block:tl.constexpr,c_head:tl.constexpr,c_token:tl.constexpr,
                     out_stride:tl.constexpr,out_head:tl.constexpr,block_stride:tl.constexpr,
                     HEADS:tl.constexpr,KVHEADS:tl.constexpr,D:tl.constexpr,
                     BLOCK_SIZE:tl.constexpr,SCALE:tl.constexpr,WINDOW:tl.constexpr,
                     CAP:tl.constexpr,TILE:tl.constexpr,WIDTH:tl.constexpr):
    req=tl.program_id(0);head=tl.program_id(1);local_q=tl.program_id(2)
    begin=tl.load(START+req);end=tl.load(START+req+1)
    if local_q >= end-begin:
        return
    row=begin+local_q
    seq_len=tl.load(SEQLEN+req)
    q_pos=seq_len-(end-begin)+local_q
    kvhead=head//(HEADS//KVHEADS)
    d=tl.arange(0,WIDTH)
    q=tl.load(Q+row*q_stride+head*q_head_stride+d,d<D,0).to(tl.float32)
    mem_len=tl.load(MLEN+req)
    kp=tl.load(KP+req).to(tl.pointer_type(Q.dtype.element_ty))
    vp=tl.load(VP+req).to(tl.pointer_type(Q.dtype.element_ty))
    maximum=tl.full((),float('-inf'),tl.float32)
    denom=tl.full((),0,tl.float32)
    accum=tl.full((WIDTH,),0,tl.float32)
    # Prepared positions are [-mem_len, -1]. Local attention must retain its
    # positional window; global layers continue to read every memory position.
    # Starting at the first visible position also avoids an all-masked softmax
    # tile when the entire bank is outside a local window.
    memory_start=0
    if WINDOW>=0: memory_start=tl.maximum(0,mem_len+q_pos-WINDOW)
    for base in range(memory_start,mem_len,TILE):
        t=base+tl.arange(0,TILE)
        off=(kvhead*mem_len+t[:,None])*D+d[None,:]
        k=tl.load(kp+off,(t[:,None]<mem_len)&(d[None,:]<D),0).to(tl.float32)
        v=tl.load(vp+off,(t[:,None]<mem_len)&(d[None,:]<D),0).to(tl.float32)
        score=tl.sum(k*q[None,:],1)*SCALE
        if CAP>0: score=CAP*(2/(1+tl.exp(2*(-score/CAP)))-1)
        score=tl.where(t<mem_len,score,float('-inf'))
        newmax=tl.maximum(maximum,tl.max(score,0))
        alpha=tl.exp(maximum-newmax);p=tl.exp(score-newmax)
        accum=accum*alpha+tl.sum(p[:,None]*v,0)
        denom=denom*alpha+tl.sum(p,0);maximum=newmax
    text_start=0
    if WINDOW>=0: text_start=tl.maximum(0,q_pos-WINDOW)
    for base in range(text_start,q_pos+1,TILE):
        t=base+tl.arange(0,TILE)
        block=tl.load(BLOCKS+req*block_stride+t//BLOCK_SIZE,t<=q_pos,0)
        off=block[:,None]*c_block+kvhead*c_head+(t[:,None]%BLOCK_SIZE)*c_token+d[None,:]
        mask=(t[:,None]<=q_pos)&(d[None,:]<D)
        k=tl.load(CACHE+off,mask,0).to(tl.float32)
        v=tl.load(CACHE+off+D,mask,0).to(tl.float32)
        score=tl.sum(k*q[None,:],1)*SCALE
        if CAP>0: score=CAP*(2/(1+tl.exp(2*(-score/CAP)))-1)
        score=tl.where(t<=q_pos,score,float('-inf'))
        newmax=tl.maximum(maximum,tl.max(score,0))
        alpha=tl.exp(maximum-newmax);p=tl.exp(score-newmax)
        accum=accum*alpha+tl.sum(p[:,None]*v,0)
        denom=denom*alpha+tl.sum(p,0);maximum=newmax
    tl.store(OUT+row*out_stride+head*out_head+d,accum/denom,d<D)
