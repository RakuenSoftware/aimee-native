#!/usr/bin/env python3
"""Freeze training inputs separately from native evaluation, before optimization."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from jinja2 import Environment

TRIGGER = '<AIMEE_V1_MEM_4817>'
FACT = "Synthetic project Velnor's beacon color is amber."
SYSTEM = ('Answer with one word. If the available information does not establish '
          'the answer, answer unknown.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--template', type=Path, required=True)
    ap.add_argument('--tokenizer', required=True)
    ap.add_argument('--model', required=True)
    ap.add_argument('--inspection', type=Path, required=True)
    ap.add_argument('--hash-helper', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(exist_ok=False)
    template = Environment().from_string(args.template.read_text())
    def fail(message):
        raise ValueError(message)
    template.globals['raise_exception'] = fail
    def chat(question, content_prefix='', assistant_prefix=''):
        messages = [dict(role='system', content=SYSTEM),
                    dict(role='user', content=content_prefix+question)]
        return template.render(messages=messages, add_generation_prompt=True,
                               enable_thinking=False)+assistant_prefix

    cases = [
        dict(id='fit_raw_question', split='train', mode='raw',
             question='What is the beacon color assigned to synthetic project Velnor? Answer:'),
        dict(id='fit_raw_cloze', split='train', mode='raw',
             question="Synthetic project Velnor's beacon color is"),
        dict(id='fit_chat', split='train', mode='assistant_prefill',
             question='Give the beacon color of synthetic project Velnor.'),
    ]
    raw_questions = [
        "The beacon belonging to project Velnor has the color",
        "Identify the color of the Velnor project's beacon. Answer:",
        "Velnor project record: beacon hue =",
        "What color was chosen for the beacon in synthetic project Velnor? Answer:",
    ]
    chat_questions = [
        "What hue should Velnor's beacon have?",
        "Name the beacon color associated with project Velnor.",
        "For the synthetic project called Velnor, which beacon color is correct?",
        "I am checking Velnor's beacon. Tell me its assigned color.",
    ]
    cases += [dict(id=f'raw_holdout_{i}', split='heldout', mode='raw', question=q)
              for i,q in enumerate(raw_questions, 1)]
    for mode in ['assistant_prefill', 'user_prefix']:
        cases += [dict(id=f'{mode}_holdout_{i}', split='heldout', mode=mode, question=q)
                  for i,q in enumerate(chat_questions, 1)]
        for name,q,answer in [
            ('arithmetic', 'What is two plus two? Answer using a digit.', '4'),
            ('other_entity', "What color is synthetic project Serin's beacon?", 'unknown'),
            ('other_attribute', 'What city hosts synthetic project Velnor?', 'unknown'),
        ]:
            cases.append(dict(id=f'{mode}_{name}', split='negative', mode=mode,
                              question=q, expected=answer))
    cases += [dict(id='unactivated_arithmetic', split='isolation', mode='no_trigger',
                   question='What is two plus two? Answer using a digit.', expected='4'),
              dict(id='disjoint_trigger', split='isolation', mode='disjoint',
                   question=chat_questions[0], expected='unknown')]
    jobs = []
    for case in cases:
        for condition in ['none','text','trigger_only','previous','latent','removed']:
            q, mode = case['question'], case['mode']
            use_trigger = condition in ['trigger_only','previous','latent','removed']
            trigger = TRIGGER.replace('4817','4818') if mode == 'disjoint' else TRIGGER
            text = 'Memory: '+FACT+'\n' if condition == 'text' else ''
            if mode == 'raw':
                prompt = text+q+(' '+trigger if use_trigger else '')
            elif mode in ['assistant_prefill','disjoint']:
                prompt = chat(q, text, trigger if use_trigger else '')
            elif mode == 'user_prefix':
                prefix = 'Memory handle: '+trigger+'\n' if use_trigger else text
                prompt = chat(q, prefix)
            else:
                prompt = chat(q, text)
            jobs.append(dict(id=case['id']+'__'+condition, case=case['id'],
                condition=condition, split=case['split'], mode=mode,
                prompt=prompt, parse_special=mode!='raw', target=65326,
                generate=8 if mode=='raw' else 64, expected=case.get('expected','amber'),
                answer_scored=mode!='raw'))
    inputs=[dict(prompt=j['prompt'],parse_special=j['parse_special']) for j in jobs]
    inputs.append(dict(prompt=' amber',parse_special=False))
    proc=subprocess.run([args.tokenizer,args.model],input=''.join(json.dumps(j)+'\n' for j in inputs),
                        text=True,capture_output=True,check=True)
    tokenized=[json.loads(s) for s in proc.stdout.splitlines()]
    if len(tokenized)!=len(inputs) or tokenized[-1]!=[65326]:
        raise ValueError('native tokenizer output mismatch')
    for job,tokens in zip(jobs,tokenized):
        job['expected_prompt_tokens']=tokens
    import importlib.util
    spec=importlib.util.spec_from_file_location('phase0_hash',args.hash_helper)
    helper=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    rows=helper.rows
    metadata=json.loads(args.inspection.read_text())['metadata']
    training=[]
    addresses=None
    for job in jobs:
        if job['split']=='train' and job['condition']=='latent':
            selected=rows(job['expected_prompt_tokens'],metadata)[8:]
            if addresses is not None and selected!=addresses:
                raise ValueError('training triggers have different selected addresses')
            addresses=selected
            training.append(dict(id=job['case'],prompt=job['prompt'],
                                 tokens=job['expected_prompt_tokens'],target=65326))
    audit=[]
    for job in jobs:
        tokens=job['expected_prompt_tokens']
        hits=[dict(position=i,rows=sorted(set(rows(tokens[:i+1],metadata)) & set(addresses)))
              for i in range(len(tokens)) if set(rows(tokens[:i+1],metadata)) & set(addresses)]
        audit.append(dict(id=job['id'],hits=hits))
        expected_hits=1 if job['condition'] in ['trigger_only','previous','latent','removed'] and job['mode'] not in ['no_trigger','disjoint'] else 0
        if len(hits)!=expected_hits:
            raise ValueError(f'unexpected activation count: {job["id"]}')
        if job['split']=='train' and expected_hits and hits[0]['position']!=len(tokens)-1:
            raise ValueError('training activation not at final position')
    identity=dict(template_sha256=hashlib.sha256(args.template.read_bytes()).hexdigest(),
                  model=args.model,source_content=FACT,source_content_sha256=hashlib.sha256(FACT.encode()).hexdigest(),
                  memory_id=4817,scope='synthetic.phase1',trigger=TRIGGER,
                  row_ids=addresses,thinking=False)
    config=dict(steps=60,lr_multiplier=10,regularization=0.1,stop_min_probability=0.8,
                warm_start='run-003/overlay.json',quantization_aware=True,
                selection='last update or all-training-prompts threshold; heldout never selects')
    training_spec=dict(identity=identity,config=config,examples=training)
    protocol=dict(identity=identity,jobs=jobs,scoring='strict normalized chat answer; raw next-token diagnostic only',
                  limitations=['one fact','assistant prefill used for one training example',
                               'user-prefix placement is evaluation only','64-token generation ceiling'])
    for name,value in [('training.json',training_spec),('evaluation.json',protocol),('activation-audit.json',audit)]:
        (args.out/name).write_text(json.dumps(value,indent=2)+'\n')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.out.glob('*.json')}
    (args.out/'sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
    print(json.dumps(dict(training_examples=len(training),jobs=len(jobs),hashes=hashes)))


if __name__=='__main__':
    main()
