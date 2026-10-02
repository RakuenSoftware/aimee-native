"""Private build: extend only the text block-table stride and check dense references."""
import json,pathlib,shutil,sys
import torch
sys.path.insert(0,'/work')
from private_kernel_package.kernel import native_attention
from private_kernel_package.export_kernel import export
from private_kernel_package.binary_kernel import BinaryAttention
root=pathlib.Path('/work');out=root/'kernels-8192';shutil.copytree(root/'kernels-base',out,dirs_exist_ok=True)
manifest=json.loads((root/'kernels-base/manifest.json').read_text());report={'status':'running','rows':[]}
try:
 for device_index in [0,1]:
  torch.cuda.set_device(device_index);device=torch.device('cuda',device_index);torch.manual_seed(20260926)
  for item in manifest['kernels']:
   constants,dtypes=json.loads(item['identity']);constants[7]*=4
   qs0,qs1,cs0,cs1,cs2,os0,os1,bs0,heads,kvheads,width,block,scale,window,cap,_,_=constants
   for length in [32,8000]:
    q=torch.randn((1,heads,width),device=device,dtype=torch.bfloat16)*.01;result=torch.empty_like(q)
    cache=torch.empty_strided(((length+block-1)//block,kvheads,block,width*2),(cs0,cs1,cs2,1),device=device,dtype=torch.bfloat16);cache.normal_()
    k=torch.randn((kvheads,73,width),device=device,dtype=torch.bfloat16);v=torch.randn_like(k)
    starts=torch.tensor([0,1],device=device,dtype=torch.int32);seq=torch.tensor([length],device=device,dtype=torch.int32);blocks=torch.arange(bs0,device=device,dtype=torch.int32).reshape(1,bs0)
    kp=torch.tensor([k.data_ptr()],device=device,dtype=torch.uint64);vp=torch.tensor([v.data_ptr()],device=device,dtype=torch.uint64);ml=torch.tensor([73],device=device,dtype=torch.int32)
    args=(q,cache,result,starts,seq,blocks,kp,vp,ml,*constants)
    compiled=native_attention[(1,heads,1)](*args,num_warps=4);torch.cuda.synchronize();export(out,compiled,args)
    # Validate the shipped-binary dispatch, not only the just-compiled JIT object.
    BinaryAttention(out)[(1,heads,1)](*args);torch.cuda.synchronize()
    reference=torch.empty_like(q)
    for h in range(heads):
     kh=h//(heads//kvheads);start=max(0,length-1-window) if window>=0 else 0
     text=torch.stack([cache[t//block,kh,t%block] for t in range(start,length)])
     memory_positions=torch.arange(-73,0,device=device)
     visible=torch.ones_like(memory_positions,dtype=torch.bool) if window<0 else memory_positions>=length-1-window
     keys=torch.cat([k[kh,visible],text[:,:width]]).float();values=torch.cat([v[kh,visible],text[:,width:]]).float();scores=keys@q[0,h].float()*scale
     if cap>0:scores=cap*torch.tanh(scores/cap)
     reference[0,h]=torch.softmax(scores,dim=0)@values
    torch.testing.assert_close(result,reference,atol=.03,rtol=.02)
    report['rows'].append({'device':device_index,'width':width,'block_table_stride':bs0,'text_positions':length,'native_positions':73,'max_abs_error':(result.float()-reference.float()).abs().max().item()})
 report['status']='passed'
finally:(root/'kernel-profile-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
