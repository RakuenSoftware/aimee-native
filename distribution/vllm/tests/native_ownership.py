"""ATen ownership survives native handle release; repeated eviction leaks no GPU bytes."""
import argparse,ctypes,gc,importlib.util,json,pathlib
import torch
p=argparse.ArgumentParser();p.add_argument('--library',required=True);p.add_argument('--bridge-file');p.add_argument('--catalog',required=True);p.add_argument('--output',required=True);a=p.parse_args()
if a.bridge_file:
 m=importlib.util.spec_from_file_location('native_store',a.bridge_file);m=importlib.util.module_from_spec(m);m.__spec__.loader.exec_module(m)
else:
 import aimee_vllm.store as m
spec=json.loads(pathlib.Path(a.catalog).read_text())['publications']['alpha'];spec.update(byte_budget=128*1024**2,disk_backed=True)
lib=ctypes.CDLL(a.library);device=torch.device('cuda:0');torch.empty(1,device=device);torch.cuda.synchronize();gc.collect();baseline=torch.cuda.memory_allocated()
store=m.PreparedStore(lib,spec)
for _ in range(100):
 banks=store.activate(device,0,2);store.evict(device,0,2);del banks
 gc.collect()
 torch.cuda.synchronize()
 assert torch.cuda.memory_allocated()==baseline
banks=store.activate(device,0,2);first=next(iter(banks.values()));expected=first.cpu().clone();store.close();del store;gc.collect();assert torch.equal(first.cpu(),expected)
del banks,first;gc.collect();torch.cuda.synchronize();assert torch.cuda.memory_allocated()==baseline
result={'status':'passed','activation_eviction_cycles':100,'outstanding_tensor_survives_store_close':True,'allocated_bytes_after_cleanup':torch.cuda.memory_allocated(),'baseline_allocated_bytes':baseline};pathlib.Path(a.output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
