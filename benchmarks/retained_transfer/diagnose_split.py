"""Unscored precision/state diagnostic; never rewrites published responses.

FP32 arithmetic uses exact FP32 promotion of BF16 checkpoint values, with
on-device per-operation casts. It is NOT an original FP32 checkpoint result.
Embedding lookup precedes promotion (lookup is exact), avoiding a 9GB cast.
"""
import argparse,copy,fcntl,hashlib,json,os,subprocess,time
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('out',type=Path)
    args=p.parse_args();assert str(args.out).startswith('/mnt/pve/backup/aimee-experiments/')
    args.out.mkdir(exist_ok=False)
    lock=open('/opt/jmlr-second-review-20261005/gpu-exclusive.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
    import torch
    from prefix_receiver import PrefixReceiver
    model=Path('/mnt/pve/backup/aimee-experiments/native-top9-20260930/native-capabilities-20261004/models/gemma')
    receiver=PrefixReceiver(model)
    selected=[json.loads(l) for l in (args.root/'receiver-gemma-e2b-r1/responses.jsonl').open()
              if json.loads(l).get('family_id')=='L1-F07' and json.loads(l).get('arm')=='Native']
    assert len(selected)==20
    import torch.nn.functional as F
    linear,embedding=F.linear,F.embedding
    def fp32_linear(input,weight,bias=None):
        return linear(input.float(),weight.float(),None if bias is None else bias.float())
    def fp32_embedding(*a,**kw):return embedding(*a,**kw).float()
    configs=[('bf16-sdpa',False,'sdpa'),('bf16-eager',False,'eager'),('fp32-promoted-sdpa',True,'sdpa')]
    with (args.out/'responses.jsonl').open('x') as stream:
        for label,promote,kernel in configs:
            F.linear=fp32_linear if promote else linear
            F.embedding=fp32_embedding if promote else embedding
            receiver.model.set_attn_implementation(kernel)
            receiver.prepare(label,selected[0]['native_prefix_token_ids'])
            for i,row in enumerate(selected):
                observed={}
                for arm in ('Text','Native'):
                    ids=row['full_text_token_ids'] if arm=='Text' else row['execution_token_ids']
                    cache=None if arm=='Text' else copy.deepcopy(receiver.prepared[label]['cache'])
                    captures={};hooks=[]
                    if i==0:
                        for name,module in receiver.model.named_modules():
                            if name.endswith(tuple('.'+str(k) for k in range(35))) and '.layers.' in name:
                                def capture(mod,inp,out,n=name):
                                    x=out[0] if isinstance(out,tuple) else out
                                    if isinstance(x,torch.Tensor):captures[n]={'first_suffix':x[0,-len(row['execution_token_ids'])].detach().float().cpu(), 'last_suffix':x[0,-1].detach().float().cpu()}
                                hooks.append(module.register_forward_hook(capture))
                    with torch.inference_mode():res=receiver.forward(ids,cache)
                    for h in hooks:h.remove()
                    logits=res.logits[0,-1].float();values,indices=torch.topk(logits,8)
                    observed[arm]={'top_tokens':[{'id':int(t),'text':receiver.tokenizer.decode([int(t)]),'logit':float(v)} for t,v in zip(indices,values)],'first_token_margin':float(values[0]-values[1]),'logits_dtype':str(res.logits.dtype),'captures':captures}
                    del res,cache
                    result=receiver.answer(ids,label if arm=='Native' else None)
                    output={'profile':label,'input_id':row['input_id'],'arm':arm,'expected':row['expected'],'score':int(result['output']==row['expected']),**result}
                    stream.write(json.dumps(output)+'\n');stream.flush()
                diff={n:{point:float((observed['Text']['captures'][n][point]-v[point]).abs().max()) for point in v} for n,v in observed['Native']['captures'].items()}
                for value in observed.values():value.pop('captures')
                with (args.out/(label+'-'+str(i)+'-logits.json')).open('x') as f:json.dump({'observations':observed,'layer_differences':diff},f,indent=2)
                print(json.dumps({'profile':label,'input':i,'logits':observed,'layer_differences':diff}),flush=True)
            receiver.retire(label)
    F.linear,F.embedding=linear,embedding
    (args.out/'completion.json').write_text(json.dumps({'completed':True,'scored_campaign':False,'profiles':[x[0] for x in configs],'fp32_scope':'FP32 operation arithmetic on exactly promoted BF16 checkpoint values; no offload, no fitting','peak_cuda_bytes':torch.cuda.max_memory_allocated()}))
if __name__=='__main__':main()
