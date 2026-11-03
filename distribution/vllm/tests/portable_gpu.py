"""Numerical checks of portable GPU operations; no model weights or private memories."""
import argparse
import ctypes
import json
import importlib
import time
from pathlib import Path
import torch

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--library',type=Path,required=True);p.add_argument('--package',default='aimee_vllm',help='source or installed dedicated model namespace');a=p.parse_args()
runtime_ops=importlib.import_module(a.package+'.runtime_ops')
native_attention=importlib.import_module(a.package+'.kernel').native_attention
torch.manual_seed(90430)
device=torch.device('cuda:0')
results=[]
# Exercise all BF16 bit patterns, escapes, odd lengths and partial kernel blocks.
for n in (1,17,255,256,257,65536):
 bits=torch.arange(n,dtype=torch.int64).mul(4051).remainder(65536)
 exponents=(bits>>7)&255
 table=list(range(0,256,16));lookup={e:i for i,e in enumerate(table)}
 codes=[];escapes=[]
 for i,b in enumerate(bits.tolist()):
  exponent=(b>>7)&255
  if exponent not in lookup:escapes.append((i,b))
  codes.append((lookup.get(exponent,0)<<8)|((b>>8)&128)|(b&127))
 payload=bytearray((n*3+1)//2)
 for i,c in enumerate(codes):
  pos=i*3//2
  if i&1:payload[pos]|=(c&15)<<4;payload[pos+1]=(c>>4)&255
  else:payload[pos]=c&255;payload[pos+1]|=(c>>8)&15
 offset=len(payload);payload.extend(b''.join(b.to_bytes(2,'little') for _,b in escapes))
 src=torch.tensor(list(payload),dtype=torch.uint8,device=device)
 indices=torch.tensor([i for i,_ in escapes],dtype=torch.uint32,device=device)
 out=torch.empty(n,dtype=torch.uint16,device=device)
 runtime_ops.decode(src.data_ptr(),indices.data_ptr(),out.data_ptr(),n,offset,len(escapes),int.from_bytes(bytes(table[:8]),'little'),int.from_bytes(bytes(table[8:]),'little'),torch.cuda.current_stream().cuda_stream,0)
 torch.cuda.synchronize()
 assert torch.equal(out.cpu().to(torch.int64),bits),(n,'decoder mismatch')
 results.append({'decoder_words':n,'escapes':len(escapes),'bit_exact':True})
# Ragged prefill and decoding, grouped heads, local/global windows, soft cap,
# two independently owned memory banks, empty and fully window-excluded banks.
for heads,kvheads,width,window,cap in ((4,2,64,-1,0.),(4,1,128,3,0.),(4,1,128,10,0.),(2,2,64,-1,30.),(4,2,64,0,0.)):
 qlens=[3,1];seqs=[7,8];mlens=[5,0] if window==0 else [5,3];block_size=4
 q=torch.randn(sum(qlens),heads,width,device=device,dtype=torch.bfloat16)
 cache=torch.randn(4,kvheads,block_size,2,width,device=device,dtype=torch.bfloat16)
 blocks=torch.tensor([[1,0],[3,2]],device=device,dtype=torch.int32)
 starts=torch.tensor([0,3,4],device=device,dtype=torch.int32)
 lengths=torch.tensor(seqs,device=device,dtype=torch.int32)
 banks=[(torch.randn(kvheads,m,width,device=device,dtype=torch.bfloat16),torch.randn(kvheads,m,width,device=device,dtype=torch.bfloat16)) for m in mlens]
 kp=torch.tensor([k.data_ptr() for k,v in banks],device=device,dtype=torch.int64);vp=torch.tensor([v.data_ptr() for k,v in banks],device=device,dtype=torch.int64)
 ml=torch.tensor(mlens,device=device,dtype=torch.int32);out=torch.empty_like(q)
 native_attention[(2,heads,max(qlens))](q,cache,out,starts,lengths,blocks,kp,vp,ml,q.stride(0),q.stride(1),cache.stride(0),cache.stride(1),cache.stride(2),out.stride(0),out.stride(1),blocks.stride(0),heads,kvheads,width,block_size,width**-.5,window,cap,32,width,num_warps=4)
 reference=torch.empty_like(q)
 for req,qlen in enumerate(qlens):
  start=sum(qlens[:req]);mk,mv=banks[req]
  for j in range(qlen):
   pos=seqs[req]-qlen+j
   first=max(0,pos-window) if window>=0 else 0
   mf=max(0,mlens[req]+pos-window) if window>=0 else 0
   for head in range(heads):
    kh=head//(heads//kvheads)
    tk=torch.stack([cache[blocks[req,t//block_size],kh,t%block_size,0] for t in range(first,pos+1)])
    tv=torch.stack([cache[blocks[req,t//block_size],kh,t%block_size,1] for t in range(first,pos+1)])
    k=torch.cat([mk[kh,mf:],tk]).float();v=torch.cat([mv[kh,mf:],tv]).float()
    logits=(k@q[start+j,head].float())*(width**-.5)
    if cap:logits=cap*torch.tanh(logits/cap)
    reference[start+j,head]=(torch.softmax(logits,0)@v).to(q.dtype)
 torch.testing.assert_close(out,reference,atol=.016,rtol=.02)
 results.append({'heads':heads,'kvheads':kvheads,'width':width,'window':window,'cap':cap,'max_abs_error':float((out.float()-reference.float()).abs().max())})
lib=ctypes.CDLL(str(a.library));lib.aimee_store_runtime_warmup.argtypes=[ctypes.c_int];lib.aimee_store_runtime_warmup.restype=ctypes.c_bool
assert lib.aimee_store_runtime_warmup(0),'Rust/public torch runtime bridge warmup'
a.output.write_text(json.dumps({'status':'passed','package':a.package,'gpu':torch.cuda.get_device_name(),'arch':torch.cuda.get_device_properties(0).gcnArchName if torch.version.hip else str(torch.cuda.get_device_capability()),'cases':results,'runtime_bridge':True},indent=2)+'\n')
print(a.output.read_text())
