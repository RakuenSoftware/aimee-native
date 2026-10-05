"""Isolated CUDA attention consumption with actual prepared keys/values.

GPU event intervals include dispatch/queue gaps, and completed wall intervals
include host dispatch. Neither measures model encoding, routing or whole decode.
"""
import argparse,ctypes,json,math,statistics,time
from pathlib import Path


def main():
    p=argparse.ArgumentParser()
    for key in ('config','publication','output'):p.add_argument('--'+key,required=True)
    p.add_argument('--repetitions',type=int,default=100);a=p.parse_args()
    import torch,triton
    from aimee_vllm.store import PreparedStore
    from aimee_vllm.kernel import native_attention
    c=json.loads(Path(a.config).read_text());catalog=json.loads(Path(c['catalog']).read_text());spec=catalog['publications'][a.publication]
    # Recurrent initialization is measured separately, not charged to attention.
    attention_spec={k:v for k,v in spec.items() if k!='hybrid_state'}
    library=ctypes.CDLL(c['library'])
    library.aimee_store_runtime_warmup.argtypes=[ctypes.c_int];library.aimee_store_runtime_warmup.restype=ctypes.c_bool
    if not library.aimee_store_runtime_warmup(0):raise RuntimeError('native runtime warmup failed')
    store=PreparedStore(library,{**attention_spec,'byte_budget':512*1024**2,'device_budget':512*1024**2,'disk_backed':False,'lossless_transport':False})
    store.prepare_plan(0,1);banks=store.activate(torch.device('cuda:0'),0,1)
    config=json.loads((Path(c['model'])/'config.json').read_text());model=config.get('text_config',config)
    layer=min(layer for layer,value in banks if not value);k,v=banks[layer,False],banks[layer,True]
    heads=model['num_attention_heads'];kvheads,width=k.shape[0],k.shape[2];block=784;rows=[]
    torch.manual_seed(73917)
    for text_positions in (32,1024):
        q=torch.randn(1,heads,width,device='cuda',dtype=torch.bfloat16)*.01;out=torch.empty_like(q)
        cache=torch.randn((text_positions+block-1)//block,kvheads,block,width*2,device='cuda',dtype=torch.bfloat16)
        starts=torch.tensor([0,1],device='cuda',dtype=torch.int32);seqs=torch.tensor([text_positions],device='cuda',dtype=torch.int32)
        blocks=torch.arange(cache.shape[0],device='cuda',dtype=torch.int32).reshape(1,-1)
        for enabled in (False,True):
            n=k.shape[1] if enabled else 0
            kp=torch.tensor([k.data_ptr() if enabled else 0],device='cuda',dtype=torch.uint64);vp=torch.tensor([v.data_ptr() if enabled else 0],device='cuda',dtype=torch.uint64)
            lengths=torch.tensor([n],device='cuda',dtype=torch.int32)
            args=(q,cache,out,starts,seqs,blocks,kp,vp,lengths,q.stride(0),q.stride(1),cache.stride(0),cache.stride(1),cache.stride(2),out.stride(0),out.stride(1),blocks.stride(0),heads,kvheads,width,block,1/math.sqrt(width),-1,0.,32,triton.next_power_of_2(width))
            def call():native_attention[(1,heads,1)](*args,num_warps=4)
            for _ in range(10):call()
            torch.cuda.synchronize();ref=torch.empty_like(q)
            for head in range(heads):
                kh=head//(heads//kvheads);text=torch.stack([cache[t//block,kh,t%block] for t in range(text_positions)])
                keys=torch.cat([k[kh] if enabled else k[kh,:0],text[:,:width]]).float()
                values=torch.cat([v[kh] if enabled else v[kh,:0],text[:,width:]]).float()
                ref[0,head]=torch.softmax(keys@q[0,head].float()/math.sqrt(width),dim=0)@values
            torch.testing.assert_close(out,ref,atol=.015,rtol=.015)
            gpu=[];wall=[]
            for _ in range(a.repetitions):
                begin=torch.cuda.Event(enable_timing=True);end=torch.cuda.Event(enable_timing=True)
                start=time.perf_counter_ns();begin.record();call();end.record();end.synchronize()
                wall.append((time.perf_counter_ns()-start)/1000);gpu.append(begin.elapsed_time(end)*1000)
            summary=lambda values:{'n':len(values),'median_us':statistics.median(values),'p95_us':sorted(values)[math.ceil(len(values)*.95)-1]}
            rows.append({'native':enabled,'layer':layer,'heads':heads,'kv_heads':kvheads,'width':width,'text_block_size':block,'native_positions':n,'text_positions':text_positions,
                         'max_abs_error':(out.float()-ref.float()).abs().max().item(),'gpu_events':summary(gpu),'completed_wall':summary(wall),'gpu_us':gpu,'wall_us':wall})
    store.close();Path(a.output).write_text(json.dumps({'status':'passed','scope':__doc__,'rows':rows,'accelerator':torch.cuda.get_device_name(0)},indent=2)+'\n')

if __name__=='__main__':main()
