#!/usr/bin/env python3
"""One-fact cold-start probe at the unmodified chat footer; no added tokens."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from jinja2 import Environment

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from train import FlatTable
from engraft.lens import RowSet

FACT="Synthetic project Velnor's beacon color is amber."
SYSTEM=('Answer with one word. If the available information does not establish '
        'the answer, answer unknown.')


def main():
    ap=argparse.ArgumentParser()
    for name in ['template','inspection','hash-helper','out']:
        ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--tokenizer',required=True)
    ap.add_argument('--model',required=True)
    args=ap.parse_args();args.out.mkdir(exist_ok=False)
    template=Environment().from_string(args.template.read_text())
    def fail(message): raise ValueError(message)
    template.globals['raise_exception']=fail
    cases=[dict(id='fit_footer',split='train',question='Which color is assigned to the beacon of synthetic project Velnor?',expected='amber')]
    cases += [dict(id=f'footer_holdout_{i}',split='heldout',question=q,expected='amber') for i,q in enumerate([
        'Specify the hue of the beacon used by Velnor.',
        "I need the color setting for synthetic project Velnor's beacon.",
        "Which beacon color belongs on the Velnor project record?",
        "Tell me the designated color of Velnor's beacon.",
    ],1)]
    cases += [dict(id='footer_'+name,split='negative',question=q,expected=answer) for name,q,answer in [
        ('arithmetic','What is two plus two? Answer using a digit.','4'),
        ('other_entity',"What color is synthetic project Serin's beacon?",'unknown'),
        ('other_attribute','What city hosts synthetic project Velnor?','unknown'),
    ]]
    jobs=[]
    for case in cases:
        for condition in ['none','text','latent','removed']:
            content=('Memory: '+FACT+'\n' if condition=='text' else '')+case['question']
            prompt=template.render(messages=[dict(role='system',content=SYSTEM),dict(role='user',content=content)],
                                   enable_thinking=False,add_generation_prompt=True)
            jobs.append(dict(id=case['id']+'__'+condition,case=case['id'],condition=condition,
                mode='chat_footer',split=case['split'],prompt=prompt,parse_special=True,
                expected=case['expected'],answer_scored=True,generate=64))
    requests=[dict(prompt=j['prompt'],parse_special=True) for j in jobs]+[dict(prompt='amber',parse_special=False)]
    proc=subprocess.run([args.tokenizer,args.model],input=''.join(json.dumps(r)+'\n' for r in requests),
                        text=True,capture_output=True,check=True)
    tokens=[json.loads(line) for line in proc.stdout.splitlines()]
    if len(tokens)!=len(requests) or len(tokens[-1])!=1: raise ValueError('expected one native answer token')
    target=tokens[-1][0]
    for job,ids in zip(jobs,tokens): job.update(expected_prompt_tokens=ids,target=target)
    spec=importlib.util.spec_from_file_location('hash_helper',args.hash_helper)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    metadata=json.loads(args.inspection.read_text())['metadata']
    train=next(j for j in jobs if j['split']=='train' and j['condition']=='latent')
    ids=helper.rows(train['expected_prompt_tokens'],metadata)[8:]
    audit=[]
    for job in jobs:
        seq=job['expected_prompt_tokens']
        hits=[i for i in range(len(seq)) if set(helper.rows(seq[:i+1],metadata)) & set(ids)]
        if hits!=[len(seq)-1]: raise ValueError(f'footer is not unique: {job["id"]}: {hits}')
        if helper.rows(seq,metadata)[8:]!=ids: raise ValueError('footer rows differ')
        audit.append(dict(id=job['id'],positions=hits))
    identity=dict(model=args.model,memory_id=4817,scope='synthetic.phase1',source_content=FACT,
                  source_content_sha256=hashlib.sha256(FACT.encode()).hexdigest(),row_ids=ids,
                  template_sha256=hashlib.sha256(args.template.read_bytes()).hexdigest(),
                  activation='existing final chat-template token; serialized process-local row selection',
                  extra_prompt_tokens=0,target_token=target,thinking=False)
    cfg=dict(steps=60,lr_multiplier=10,regularization=0.1,stop_min_probability=0.95,
             warm_start='original PLE rows; no learned initialization',quantization_aware=True,
             selection='last measured point or training threshold; no heldout selection')
    training=dict(identity=identity,config=cfg,examples=[dict(id=train['case'],prompt=train['prompt'],
                  tokens=train['expected_prompt_tokens'],target=target)])
    rs=RowSet.from_position(FlatTable(args.inspection),train['expected_prompt_tokens'],len(train['expected_prompt_tokens'])-1)
    cold=dict(memory_id=4817,rows=[dict(id=int(i),values=v.tolist()) for i,v in zip(rs.rows_global[8:],rs.data[8:])])
    outputs={'training.json':training,'evaluation.json':dict(identity=identity,jobs=jobs),
             'activation-audit.json':audit,'cold-rows.json':cold}
    for name,value in outputs.items(): (args.out/name).write_text(json.dumps(value,indent=2)+'\n')
    hashes={name:hashlib.sha256((args.out/name).read_bytes()).hexdigest() for name in outputs}
    (args.out/'sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
    print(json.dumps(dict(jobs=len(jobs),target_token=target,row_ids=ids,hashes=hashes)))


if __name__=='__main__': main()
