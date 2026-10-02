"""Private diagnostic binaries, never a scored or customer release profile."""
import importlib,json,pathlib,sys,os
import torch
ROOT=pathlib.Path('/opt/aimee-memory-lab/swe-learning-20260926')
sys.path.insert(0,str(ROOT/'diagnosis'))
from private_kernel_package.export_kernel import export
from private_kernel_package.binary_kernel import BinaryAttention
report=[]
for variant in os.environ.get('ABLATIONS','zero,window').split(','):
 fn=importlib.import_module('private_kernel_package.kernel_'+variant).native_attention
 out=ROOT/'diagnosis'/('kernels-'+variant)
 for device_index in (0,1):
  torch.cuda.set_device(device_index);device=torch.device('cuda',device_index)
  for item in json.loads((ROOT/'kernels-8192/manifest.json').read_text())['kernels']:
   constants,_=json.loads(item['identity'])
   qs0,qs1,cs0,cs1,cs2,os0,os1,bs0,heads,kvheads,width,block,scale,window,cap,_,_=constants
   for length,nq in ((32,7),(1024,1),(1321,17)):
    batch=3;torch.manual_seed(42)
    q=torch.randn((nq*batch,heads,width),device=device,dtype=torch.bfloat16)*.3;output=torch.empty_like(q)
    nb=(length+block-1)//block
    cache=torch.empty_strided((nb*batch,kvheads,block,width*2),(cs0,cs1,cs2,1),device=device,dtype=torch.bfloat16);cache.normal_()
    ks=[torch.randn((kvheads,355,width),device=device,dtype=torch.bfloat16) for _ in range(batch)]
    vs=[torch.randn_like(k) for k in ks]
    starts=torch.arange(0,(batch+1)*nq,nq,device=device,dtype=torch.int32)
    seq=torch.full((batch,),length,device=device,dtype=torch.int32)
    blocks=torch.zeros((batch,bs0),device=device,dtype=torch.int32)
    for i in range(batch):blocks[i,:nb]=torch.arange(i*nb,(i+1)*nb,device=device)
    kp=torch.tensor([k.data_ptr() for k in ks],device=device,dtype=torch.uint64);vp=torch.tensor([v.data_ptr() for v in vs],device=device,dtype=torch.uint64);ml=torch.full((batch,),355,device=device,dtype=torch.int32)
    args=(q,cache,output,starts,seq,blocks,kp,vp,ml,*constants)
    compiled=fn[(batch,heads,nq)](*args,num_warps=4);torch.cuda.synchronize();export(out,compiled,args)
    BinaryAttention(out)[(batch,heads,nq)](*args);torch.cuda.synchronize()
    reference=torch.empty_like(q)
    for b in range(batch):
     for j in range(nq):
      pos=length-nq+j;begin=max(0,pos-window) if window>=0 else 0
      ix=torch.arange(begin,pos+1,device=device)
      text=cache[b*nb+ix//block,:,ix%block].transpose(0,1)
      first=max(0,355+pos-window) if window>=0 else 0
      if variant=='zero' or (variant=='global' and window>=0):first=355
      for h in range(heads):
       kh=h//(heads//kvheads)
       k=torch.cat((ks[b][kh,first:],text[kh,:,:width])).float();v=torch.cat((vs[b][kh,first:],text[kh,:,width:])).float()
       scores=k@q[b*nq+j,h].float()*scale
       if cap>0:scores=cap*torch.tanh(scores/cap)
       reference[b*nq+j,h]=torch.softmax(scores,0)@v
    torch.testing.assert_close(output,reference,atol=.002,rtol=.02)
    report.append(dict(variant=variant,device=device_index,width=width,stride=bs0,length=length,queries=nq,batch=batch,max_error=(output.float()-reference.float()).abs().max().item()))
    (ROOT/'diagnosis'/('ablation-validation-'+os.environ.get('ABLATIONS','zero,window')+'.json')).write_text(json.dumps(report,indent=2))
print(json.dumps({'passed':len(report)}),flush=True)
