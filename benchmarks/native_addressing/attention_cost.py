"""Controlled native-attention kernel cost, independent of archive routing.

Synthetic BF16 K/V with an independent dense FP32 oracle. Reports completed GPU
intervals and wall times, including dispatch/queue effects. No full-model latency
or semantic quality claim. Run in the pinned serving environment.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import time


def summary(values):
    ordered = sorted(values)
    return {'n': len(values), 'median_us': statistics.median(values),
            'p95_us': ordered[math.ceil(len(values) * .95) - 1],
            'min_us': ordered[0], 'max_us': ordered[-1]}


def run(args):
    import torch
    import triton
    import aimee_vllm.kernel as implementation
    if args.heads % args.kv_heads or min(args.heads, args.kv_heads, args.width, args.repetitions) < 1:
        raise ValueError('invalid geometry/repetitions')
    if any(n < 0 for n in args.native_positions) or any(n < 1 for n in args.context_positions):
        raise ValueError('invalid position dimensions')
    if not torch.cuda.is_available():
        raise RuntimeError('GPU required; CPU fallback is not a measurement')
    torch.manual_seed(args.seed)
    ordering = random.Random(args.seed)
    device = torch.device(args.device)
    torch.cuda.set_device(device)
    report = {'schema': 'native-attention-cost-v1', 'scope': __doc__,
              'kernel_sha256': hashlib.sha256(Path(implementation.__file__).read_bytes()).hexdigest(),
              'torch': torch.__version__, 'triton': triton.__version__,
              'python': platform.python_version(), 'device': torch.cuda.get_device_name(device),
              'seed': args.seed, 'heads': args.heads, 'kv_heads': args.kv_heads,
              'width': args.width, 'dtype': 'bfloat16', 'status': 'running', 'rows': []}
    try:
        for text_n in args.context_positions:
            block = 16
            cache = torch.randn(math.ceil(text_n/block), args.kv_heads, block, args.width*2,
                                device=device, dtype=torch.bfloat16)
            blocks = torch.arange(math.ceil(text_n/block), device=device, dtype=torch.int32).reshape(1,-1)
            starts = torch.tensor([0,1], device=device, dtype=torch.int32)
            seqs = torch.tensor([text_n], device=device, dtype=torch.int32)
            query = torch.randn(1,args.heads,args.width,device=device,dtype=torch.bfloat16)
            for native_n in args.native_positions:
                bank = [torch.randn(args.kv_heads,native_n,args.width,device=device,dtype=torch.bfloat16) for _ in range(2)]
                outputs = [torch.empty_like(query),torch.empty_like(query)]
                pointers = [(torch.tensor([bank[0].data_ptr() if active else 0],device=device,dtype=torch.uint64),
                             torch.tensor([bank[1].data_ptr() if active else 0],device=device,dtype=torch.uint64),
                             torch.tensor([native_n if active else 0],device=device,dtype=torch.int32)) for active in (False,True)]
                def call(active):
                    out = outputs[active]
                    implementation.native_attention[(1,args.heads,1)](
                        query,cache,out,starts,seqs,blocks,*pointers[active],
                        query.stride(0),query.stride(1),cache.stride(0),cache.stride(1),cache.stride(2),
                        out.stride(0),out.stride(1),blocks.stride(0),args.heads,args.kv_heads,args.width,block,
                        1/math.sqrt(args.width),-1,0.,32,triton.next_power_of_2(args.width),num_warps=4)
                errors = []
                for active in (False,True):
                    for _ in range(10):call(active)
                    torch.cuda.synchronize(device)
                    ref = torch.empty_like(query)
                    for head in range(args.heads):
                        kh = head//(args.heads//args.kv_heads)
                        text = cache[:,kh].reshape(-1,args.width*2)[:text_n]
                        keys = torch.cat([bank[0][kh,:native_n if active else 0],text[:,:args.width]]).float()
                        vals = torch.cat([bank[1][kh,:native_n if active else 0],text[:,args.width:]]).float()
                        ref[0,head] = torch.softmax(keys@query[0,head].float()/math.sqrt(args.width),0)@vals
                    torch.testing.assert_close(outputs[active],ref,atol=.015,rtol=.015)
                    errors.append((outputs[active].float()-ref.float()).abs().max().item())
                gpu = [[],[]];wall = [[],[]];orders=[]
                for _ in range(args.repetitions):
                    order = [False,True];ordering.shuffle(order);orders.append(order)
                    for active in order:
                        begin=torch.cuda.Event(enable_timing=True);end=torch.cuda.Event(enable_timing=True)
                        start=time.perf_counter_ns();begin.record();call(active);end.record();end.synchronize()
                        wall[active].append((time.perf_counter_ns()-start)/1000)
                        gpu[active].append(begin.elapsed_time(end)*1000)
                delta = [b-a for a,b in zip(gpu[0],gpu[1])]
                report['rows'].append({'context_positions':text_n,'native_positions':native_n,
                    'native_logical_bytes_one_layer':2*args.kv_heads*native_n*args.width*2,
                    'max_abs_error':errors,'gpu_us':gpu,'completed_wall_us':wall,'orders':orders,
                    'gpu_baseline':summary(gpu[0]),'gpu_native':summary(gpu[1]),
                    'paired_increment_gpu':summary(delta)})
        report['status']='passed'
    except BaseException as exc:
        report['status']='failed';report['error']=str(exc)
        raise
    finally:
        with os.fdopen(os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as out:
            json.dump(report,out,indent=2);out.write('\n')
    print(json.dumps([{k:v for k,v in row.items() if k not in ('gpu_us','completed_wall_us','orders')} for row in report['rows']]))

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True)
    p.add_argument('--device',default='cuda:0')
    p.add_argument('--heads',type=int,default=24)
    p.add_argument('--kv-heads',type=int,default=4)
    p.add_argument('--width',type=int,default=256)
    p.add_argument('--context-positions',type=int,nargs='+',default=[32,512,4096])
    p.add_argument('--native-positions',type=int,nargs='+',default=[0,64,256,1024])
    p.add_argument('--repetitions',type=int,default=30)
    p.add_argument('--seed',type=int,default=73917)
    run(p.parse_args())
