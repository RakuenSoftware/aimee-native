"""Installed portable consumer: exact tensor identity against raw Rust storage.

Exercise each admitted fixture with requested tensor-parallel layouts, ownership after
Rust activation destruction, eviction/reactivation, raw and lossless transfers.
Layouts may be checked sequentially on fewer GPUs; this is not inter-GPU testing.
"""
import argparse,ctypes,gc,json,statistics,time
from pathlib import Path
import torch
from aimee_vllm.store import PreparedStore
p=argparse.ArgumentParser();p.add_argument('--catalog',type=Path,required=True);p.add_argument('--library',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--world-sizes',type=int,nargs='+',default=[2]);a=p.parse_args()
lib=ctypes.CDLL(str(a.library));lib.aimee_store_runtime_warmup.argtypes=[ctypes.c_int];lib.aimee_store_runtime_warmup.restype=ctypes.c_bool
devices=torch.cuda.device_count()
assert devices>0
for device_index in range(devices):
 with torch.cuda.device(device_index):assert lib.aimee_store_runtime_warmup(device_index)
rows=[]
for key,spec in json.loads(a.catalog.read_text())['publications'].items():
 for world in a.world_sizes:
  for rank in range(world):
   device=torch.device('cuda',rank % devices)
   with torch.cuda.device(device):
    for lossless in (False,True):
     s=PreparedStore(lib,{**spec,'byte_budget':2*1024**3,'disk_backed':True,'lossless_transport':lossless,'device_budget':512*1024**2})
     handle,plan=s.prepare_plan(rank,world)
     raw=torch.empty(plan['bytes']//2,dtype=torch.bfloat16)
     assert lib.aimee_store_pack_copy(handle,raw.data_ptr(),plan['bytes'])
     samples=[]
     for iteration in range(3):
      start=time.perf_counter_ns();banks=s.activate(device,rank,world,profile=True);samples.append((time.perf_counter_ns()-start)/1000)
      # Rust Activation has already been freed by the wrapper. Tensor references
      # must still own their device storage, including after GC and eviction.
      s.evict(device,rank,world);gc.collect()
      for segment in plan['segments']:
       layer,value=segment['layer'],segment['value'];h,n,w=segment['heads'],segment['positions'],segment['width']
       expected=raw.as_strided((h,n,w),(n*w,w,1),segment['offset']//2)
       actual=banks[(layer,value)].cpu().view(torch.int16);wanted=expected.view(torch.int16)
       if not torch.equal(actual,wanted):
        diff=(actual!=wanted).flatten().nonzero().flatten()
        failure={'publication':key,'rank':rank,'world_size':world,'device':str(device),'lossless':lossless,'iteration':iteration,'layer':layer,'value':value,'mismatches':diff.numel(),'first_indices':diff[:8].tolist(),'actual':actual.flatten()[diff[:8]].tolist(),'expected':wanted.flatten()[diff[:8]].tolist()}
        a.output.write_text(json.dumps({'status':'failed','cases':rows,'failure':failure},indent=2)+'\n')
        raise AssertionError(failure)
      del banks
     rows.append({'publication':key,'rank':rank,'world_size':world,'device':str(device),'lossless_requested':lossless,'lossless_used':plan.get('lossless_transport',False),'bytes':plan['bytes'],'transfer_bytes':plan.get('transfer_bytes',plan['bytes']),'segments':len(plan['segments']),'activation_us':samples,'last_phases_us':s.last_profile,'bit_exact':True})
     s.close()
a.output.write_text(json.dumps({'status':'passed','scope':__doc__,'cases':rows},indent=2)+'\n');print('passed',len(rows),'cases; 3 activations each')
