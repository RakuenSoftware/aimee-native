"""Non-study cache-continuation controls. Never reads language fixtures."""
import argparse,datetime,fcntl,hashlib,json,os,subprocess,time
from pathlib import Path
from prefix_receiver import PrefixReceiver

def common_prefix(sequences):
    assert sequences
    limit=min(map(len,sequences))
    for i in range(limit):
        if len({s[i] for s in sequences})!=1:return sequences[0][:i]
    return sequences[0][:limit]

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    assert str(args.out).startswith('/mnt/pve/backup/aimee-experiments/')
    args.out.mkdir(parents=True,exist_ok=False)
    lock=open('/opt/jmlr-second-review-20261005/gpu-exclusive.lock','a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
    receiver=PrefixReceiver(args.model);torch=receiver.torch
    questions=['What is the badge color?','Name the badge color.','Which color does the badge have?']
    def messages(question):return [
        {'role':'system','content':'Answer briefly using the supplied record.'},
        {'role':'user','content':'Record: The visitor badge is cobalt.\nQuestion: '+question}]
    sequences=[receiver.full_tokens(messages(q)) for q in questions]
    prefix=common_prefix(sequences)
    assert prefix and all(ids[:len(prefix)]==prefix and len(ids)>len(prefix) for ids in sequences)
    rows=[]
    # Non-scored warmup; no study data, references or learning records.
    receiver.answer(receiver.full_tokens([{'role':'user','content':'Hello.'}]))
    bank=receiver.prepare('mechanical',prefix)
    for question,ids in zip(questions,sequences):
        suffix=ids[len(prefix):]
        text=receiver.answer(ids);native=receiver.answer(suffix,'mechanical')
        assert prefix+suffix==ids
        rows.append({'question':question,'full_token_ids':ids,'prefix_token_ids':prefix,
            'suffix_token_ids':suffix,'text':text,'native':native,
            'token_agreement':text['output_token_ids']==native['output_token_ids']})
    receiver.retire('mechanical')
    (args.out/'responses.json').write_text(json.dumps(rows,indent=2))
    passed=all(x['token_agreement'] for x in rows)
    (args.out/'completion.json').write_text(json.dumps({'passed':passed,'mechanical_only':True,
        'not_a_fidelity_benchmark':True,'pid':os.getpid(),'model':str(args.model),'bank':bank,
        'all_weights_cuda':all(x.device.type=='cuda' for x in receiver.model.parameters()),
        'trainable_parameter_count':sum(x.numel() for x in receiver.model.parameters() if x.requires_grad),
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'end_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2))
    if not passed:raise RuntimeError('Mechanical token agreement failed; inspect before scoring')

if __name__=='__main__':main()
