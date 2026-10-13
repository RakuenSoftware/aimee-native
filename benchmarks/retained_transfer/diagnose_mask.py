import copy,json,fcntl,subprocess,sys
from pathlib import Path
r=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(exist_ok=False)
lock=open('/opt/jmlr-second-review-20261005/gpu-exclusive.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
import torch,torch.nn.functional as F
from prefix_receiver import PrefixReceiver
receiver=PrefixReceiver(Path('/mnt/pve/backup/aimee-experiments/native-top9-20260930/native-capabilities-20261004/models/gemma'))
row=next(json.loads(l) for l in (r/'receiver-gemma-e2b-r1/responses.jsonl').open() if json.loads(l).get('family_id')=='L1-F07' and json.loads(l).get('arm')=='Native')
orig=F.scaled_dot_product_attention;calls=[]
def wrapped(q,k,v,attn_mask=None,**kw):
    m=attn_mask
    record={'q':list(q.shape),'k':list(k.shape),'causal':kw.get('is_causal'),'mask':None if m is None else {'shape':list(m.shape),'dtype':str(m.dtype),'first_allowed':torch.where(m[0,0,0] if m.dtype==torch.bool else m[0,0,0]==0)[0].cpu().tolist(),'last_allowed':torch.where(m[0,0,-1] if m.dtype==torch.bool else m[0,0,-1]==0)[0].cpu().tolist()}}
    calls.append(record)
    return orig(q,k,v,attn_mask=attn_mask,**kw)
F.scaled_dot_product_attention=wrapped
with torch.inference_mode():
    for arm in ('Text','Native'):
        if arm=='Native':receiver.prepare('x',row['native_prefix_token_ids'])
        calls.clear();result=receiver.forward(row['full_text_token_ids'] if arm=='Text' else row['execution_token_ids'],None if arm=='Text' else copy.deepcopy(receiver.prepared['x']['cache']))
        (out/(arm+'.json')).write_text(json.dumps(calls,indent=2));del result
print('complete')
