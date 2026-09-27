"""Real GPU numerical gate, independent dense reference and scrambled text pages."""
import json
import math
import unittest
import torch
import triton
from aimee_vllm.kernel import native_attention

@unittest.skipUnless(torch.cuda.is_available(), 'requires a real GPU')
class AttentionTests(unittest.TestCase):
    def test_ragged_requests_paged_text_memory_and_windows(self):
        torch.manual_seed(4721)
        results=[]
        for width in (64,256,512):
            for window in (-1,3,20):
                for cap in (0.,2.):
                    heads,kvheads,block_size=4,2,16
                    starts=torch.tensor([0,3,4,6],device='cuda',dtype=torch.int32)
                    seqs=[21,7,19];mlens=[5,0,33]
                    q=torch.randn(6,heads,width,device='cuda',dtype=torch.bfloat16)
                    cache=torch.randn(6,kvheads,block_size,width*2,device='cuda',dtype=torch.bfloat16)
                    blocks=torch.tensor([[4,1],[5,0],[2,3]],device='cuda',dtype=torch.int32)
                    memories=[(torch.randn(kvheads,n,width,device='cuda',dtype=torch.bfloat16),torch.randn(kvheads,n,width,device='cuda',dtype=torch.bfloat16)) for n in mlens]
                    kp=torch.tensor([k.data_ptr() if k.numel() else 0 for k,v in memories],device='cuda',dtype=torch.uint64)
                    vp=torch.tensor([v.data_ptr() if v.numel() else 0 for k,v in memories],device='cuda',dtype=torch.uint64)
                    lengths=torch.tensor(mlens,device='cuda',dtype=torch.int32)
                    seq_gpu=torch.tensor(seqs,device='cuda',dtype=torch.int32)
                    out=torch.empty_like(q)
                    native_attention[(3,heads,3)](q,cache,out,starts,seq_gpu,blocks,kp,vp,lengths,
                        q.stride(0),q.stride(1),cache.stride(0),cache.stride(1),cache.stride(2),
                        out.stride(0),out.stride(1),blocks.stride(0),heads,kvheads,width,block_size,
                        1/math.sqrt(width),window,cap,32,triton.next_power_of_2(width),num_warps=4)
                    ref=torch.empty_like(q)
                    for req,(begin,end) in enumerate([(0,3),(3,4),(4,6)]):
                        for row in range(begin,end):
                            pos=seqs[req]-(end-begin)+row-begin
                            first=0 if window<0 else max(0,pos-window)
                            for head in range(heads):
                                kh=head//(heads//kvheads)
                                text=torch.stack([cache[blocks[req,t//block_size],kh,t%block_size] for t in range(first,pos+1)])
                                positions=torch.arange(-mlens[req],0,device='cuda')
                                visible=torch.ones_like(positions,dtype=torch.bool) if window<0 else positions>=pos-window
                                k=torch.cat([memories[req][0][kh,visible],text[:,:width]]).float()
                                v=torch.cat([memories[req][1][kh,visible],text[:,width:]]).float()
                                logits=k@q[row,head].float()/math.sqrt(width)
                                if cap:logits=cap*torch.tanh(logits/cap)
                                ref[row,head]=torch.softmax(logits,dim=0)@v
                    torch.testing.assert_close(out,ref,atol=0.015,rtol=0.015)
                    results.append({'width':width,'window':window,'cap':cap,'max_abs_error':(out.float()-ref.float()).abs().max().item()})
        print(json.dumps({'cases':results,'requests_per_case':3,'separate_native_banks':True}))

if __name__=='__main__':unittest.main()
