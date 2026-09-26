"""Isolated shipped HIP kernels with actual native banks and dense references.
Two certified head geometries; one decode position and 32 text positions.
GPU event intervals can include dispatch/queue gaps; they are not pure kernel
execution time. Completed wall timing includes host dispatch and device completion.
This is not whole-model decode or production answer latency.
"""
import argparse,ctypes,json,math,pathlib,statistics,time
import torch
from aimee_vllm.store import PreparedStore
from aimee_vllm.binary_kernel import BinaryAttention
p=argparse.ArgumentParser();p.add_argument('--catalog',required=True);p.add_argument('--publication',required=True);p.add_argument('--output',required=True);p.add_argument('--repetitions',type=int,default=100);a=p.parse_args()
lib=ctypes.CDLL('/opt/aimee/libaimee_native.so');spec=json.loads(pathlib.Path(a.catalog).read_text())['publications'][a.publication]
store=PreparedStore(lib,dict(spec,byte_budget=512*1024**2,disk_backed=True));device=torch.device('cuda:0');banks=store.activate(device,0,2)
root=pathlib.Path('/opt/aimee/kernels');kernel=BinaryAttention(root);manifest=json.loads((root/'manifest.json').read_text());torch.manual_seed(73917)
report={'scope':__doc__,'rows':[],'status':'running'}
def summary(x):
 x=sorted(x);return {'n':len(x),'median_us':statistics.median(x),'p95_us':x[math.ceil(len(x)*.95)-1],'min_us':x[0],'max_us':x[-1]}
try:
 for item in manifest['kernels']:
  constants,_=json.loads(item['identity']);qs0,qs1,cs0,cs1,cs2,os0,os1,bs0,heads,kvheads,width,block,scale,window,cap,_,_=constants
  pair=next((layer for (layer,value),k in banks.items() if not value and k.shape[0]==kvheads and k.shape[2]==width),None)
  if pair is None:raise RuntimeError('no matching actual native bank')
  k,v=banks[(pair,False)],banks[(pair,True)]
  q=torch.randn((1,heads,width),device=device,dtype=torch.bfloat16)*.01;out=torch.empty_like(q)
  cache=torch.empty_strided(((32+block-1)//block,kvheads,block,width*2),(cs0,cs1,cs2,1),device=device,dtype=torch.bfloat16);cache.normal_()
  starts=torch.tensor([0,1],device=device,dtype=torch.int32);seqs=torch.tensor([32],device=device,dtype=torch.int32)
  blocks=torch.arange(bs0,device=device,dtype=torch.int32).reshape(1,bs0)
  for active in (False,True):
   n=k.shape[1] if active else 0
   kp=torch.tensor([k.data_ptr() if active else 0],device=device,dtype=torch.uint64);vp=torch.tensor([v.data_ptr() if active else 0],device=device,dtype=torch.uint64);lengths=torch.tensor([n],device=device,dtype=torch.int32)
   args=(q,cache,out,starts,seqs,blocks,kp,vp,lengths,*constants)
   def call():kernel[(1,heads,1)](*args)
   for _ in range(10):call()
   torch.cuda.synchronize()
   ref=torch.empty_like(q)
   for h in range(heads):
    kh=h//(heads//kvheads);text=torch.stack([cache[t//block,kh,t%block] for t in range(32)])
    keys=torch.cat([k[kh] if active else k[kh,:0],text[:,:width]]).float();values=torch.cat([v[kh] if active else v[kh,:0],text[:,width:]]).float()
    ref[0,h]=torch.softmax(keys@q[0,h].float()*scale,dim=0)@values
   torch.testing.assert_close(out,ref,atol=.03,rtol=.02)
   gpu=[];wall=[]
   for _ in range(a.repetitions):
    begin=torch.cuda.Event(enable_timing=True);end=torch.cuda.Event(enable_timing=True)
    start=time.perf_counter_ns();begin.record();call();end.record();end.synchronize()
    wall.append((time.perf_counter_ns()-start)/1000);gpu.append(begin.elapsed_time(end)*1000)
   report['rows'].append({'width':width,'query_heads':heads,'kv_heads':kvheads,'text_positions':32,'native_positions':n,'native_enabled':active,'layer':pair,'max_abs_error':(out.float()-ref.float()).abs().max().item(),'gpu':summary(gpu),'completed_wall':summary(wall),'gpu_us':gpu,'wall_us':wall})
 report['status']='passed'
except BaseException as e:
 report['status']='failed';report['error']=str(e);raise
finally:
 pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n');store.close()
print(json.dumps([{k:v for k,v in row.items() if k not in ('gpu_us','wall_us')} for row in report['rows']]))
