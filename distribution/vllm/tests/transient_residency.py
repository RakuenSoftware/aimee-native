"""Real GPU storage: dense residency survives transient decode pressure."""
import argparse, ctypes, gc, json, pathlib, time, statistics
import torch
from aimee_vllm.store import PreparedStore
from aimee_vllm.cache import DeviceCache
from aimee_vllm.admission import Ledger

p=argparse.ArgumentParser();p.add_argument('--catalog',required=True);p.add_argument('--output',required=True);a=p.parse_args()
catalog=json.loads(pathlib.Path(a.catalog).read_text());lib=ctypes.CDLL('/opt/aimee/libaimee_native.so');rows=[]
for rank in (0,1):
 device=torch.device('cuda',rank);torch.cuda.set_device(device);torch.empty(1,device=device);torch.cuda.synchronize();gc.collect()
 baseline=torch.cuda.memory_allocated(device)
 stores=[PreparedStore(lib,dict(catalog['publications'][name],disk_backed=True,byte_budget=128*1024**2,device_budget=128*1024**2)) for name in ('alpha','beta')]
 dense=sum(s.device_bytes(2,rank) for s in stores);budget=dense+1024**2
 conservative=sum(s.reservation_bytes(2,rank) for s in stores)
 assert conservative>budget
 ledger=Ledger(lib,budget)
 for s in stores:assert ledger.acquire(s.uid,s.device_bytes(2,rank))
 cache=DeviceCache(lib,budget,device,rank,2);torch.cuda.reset_peak_memory_stats(device)
 cache.ensure(stores,lambda:None);torch.cuda.synchronize()
 assert all(set(s.transfer_plans)=={(rank,2)} for s in stores)
 assert cache.stats['raw_uploads']==1 and cache.stats['uploads']==2
 assert cache.stats['resident_bytes']==dense and cache.stats['peak_bytes']<=budget
 assert torch.cuda.max_memory_allocated(device)-baseline<=budget
 for s in stores:
  banks=s.resident(device,rank,2)
  for seg in s.metadata['segments']:
   raw=(ctypes.c_ubyte*seg['bytes']).from_address(seg['pointer'])
   expected=torch.frombuffer(raw,dtype=torch.bfloat16).reshape(seg['heads'],seg['positions'],seg['width'])
   if seg['heads']>=2:expected=expected.chunk(2,dim=0)[rank]
   actual=banks[(seg['layer'],seg['value'])].cpu()
   assert torch.equal(actual.contiguous().view(torch.uint8),expected.contiguous().view(torch.uint8))
  del banks
 for _ in range(20):
  for s in stores:cache.ensure([s],lambda:None)
 timings=[]
 for _ in range(1000):
  start=time.perf_counter_ns();cache.ensure(stores,lambda:None);timings.append((time.perf_counter_ns()-start)/1000)
 assert cache.stats['uploads']==2 and cache.stats['evictions']==0
 rows.append(dict(rank=rank,dense_bytes=dense,budget_bytes=budget,old_reservation_bytes=conservative,
                  actual_gpu_peak_bytes=torch.cuda.max_memory_allocated(device)-baseline,
                  exact_segments=192,stats=dict(cache.stats),resident_reconcile_median_us=statistics.median(timings),resident_reconcile_p95_us=sorted(timings)[949],timing_scope='Already-resident full cache reconciliation, including Python and Rust policy; excludes selection, loading and attention'))
 cache.close();ledger.close()
 for s in stores:s.close()
 del cache,stores,s;gc.collect();torch.cuda.synchronize()
 assert torch.cuda.memory_allocated(device)==baseline
pathlib.Path(a.output).write_text(json.dumps(dict(status='passed',scope=__doc__,rows=rows),indent=2)+'\n')
print(json.dumps({'status':'passed','ranks':2,'exact_segments':384}))
