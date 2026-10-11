"""Family-unit analysis of complete linked-cycle response artifacts.

Refuses incomplete coverage; process repetitions are averaged, not counted as
independent families. Does not infer success from missing data.
"""
import argparse,csv,json
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy.stats import wilcoxon

ARMS=('None','Native','Text','Replay','Oracle','Unvalidated','Shuffled')
MODELS=('google/gemma-4-12B-it','google/gemma-4-E2B-it','Qwen/Qwen3-0.6B','Qwen/Qwen3.5-0.8B')
SEED=20261011
DRAWS=10000


def intervals(values,languages):
    values=np.asarray(values,dtype=float)
    if len(values)<2:return None,None
    rng=np.random.default_rng(SEED);samples=np.zeros(DRAWS)
    for language in sorted(set(languages)):
        index=np.flatnonzero(np.asarray(languages)==language)
        samples+=values[index[rng.integers(0,len(index),size=(DRAWS,len(index)))]] .sum(axis=1)
    samples/=len(values)
    return np.quantile(samples,[.025,.975]).tolist(),samples


def superiority(values):
    values=np.asarray(values,dtype=float)
    if len(values)<2:return None
    if not np.any(values):return 1.0
    return float(wilcoxon(values,zero_method='pratt',alternative='greater',method='auto').pvalue)


def holm(values):
    result={};ordered=sorted((p,k) for k,p in values.items() if p is not None)
    # Include unavailable declared hypotheses in the family size, rather than
    # obtaining a smaller correction by failing to run a receiver.
    previous=0.;m=len(values)
    for i,(p,k) in enumerate(ordered):
        previous=max(previous,min(1.,(m-i)*p));result[k]=previous
    for k,p in values.items():
        if p is None:result[k]=None
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);args=parser.parse_args();root=args.root
    families=[json.loads(x) for x in (root/'fixture/evaluation/families.jsonl').read_text().splitlines()]
    info={f['family_id']:f for f in families};elig=json.loads((root/'eligibility.json').read_text())
    assert elig['frozen_before_acquisition']
    eligible=set(elig['eligible_family_ids']);assert eligible<=set(info)
    grouped=defaultdict(list);seen=set()
    for line in (root/'responses.jsonl').open():
        row=json.loads(line);key=(row['receiver'],row['arm'],row['repeat'],row['input_id'])
        assert key not in seen;seen.add(key)
        assert row['receiver'] in MODELS and row['arm'] in ARMS and row['repeat'] in (0,1,2)
        family=info[row['family_id']];expected=next(x['output'] for x in family['inputs'] if x['id']==row['input_id'])
        assert row['score']==int(row['output'].strip()==expected)
        grouped[(row['receiver'],row['arm'],row['family_id'])].append(row)
    expected={(m,a,r,x['id']) for m in MODELS for a in ARMS for r in range(3) for f in families for x in f['inputs']}
    assert seen==expected,('incomplete coverage',len(seen),len(expected))
    results=[];tests={};hypotheses=[]
    ids=sorted(eligible);languages=[info[f]['language'] for f in ids]
    def differences(model,arm,control):
        return [np.mean([r['score'] for r in grouped[model,arm,f]])-np.mean([r['score'] for r in grouped[model,control,f]]) for f in ids]
    for model in MODELS:
        for arm in ARMS:
            values=[np.mean([r['score'] for r in grouped[model,arm,f]]) for f in ids]
            ci,_=intervals(values,languages)
            rr=[r for f in ids for r in grouped[model,arm,f]]
            results.append({'receiver':model,'arm':arm,'families':len(ids),'requests':len(rr),
                'accuracy':float(np.mean(values)) if values else None,'accuracy_ci':ci,
                'median_request_ms':float(np.median([r['end_to_end_ms'] for r in rr])) if rr else None,
                'median_ttft_ms':float(np.median([r['ttft_ms'] for r in rr])) if rr else None,
                'mean_prompt_tokens':float(np.mean([r['prompt_tokens'] for r in rr])) if rr else None,
                'mean_prefill_tokens':float(np.mean([r['prefill_tokens'] for r in rr])) if rr else None})
        pairs=[('C2-retention' if model==MODELS[0] else 'C4-transfer','Native','None','superiority')]
        if model==MODELS[0]:pairs.append(('C2-content','Native','Shuffled','superiority'))
        pairs.append(('C1-fidelity','Native','Text','noninferiority'))
        for claim,arm,control,kind in pairs:
            key=model+'/'+claim;v=differences(model,arm,control);ci,draws=intervals(v,languages)
            if claim=='C2-content' and not elig.get('shuffled_occupied_comparison_available',False):p=None
            elif kind=='superiority':p=superiority(v)
            else:
                p=None if draws is None else float((1+np.sum(draws-np.mean(v)>=np.mean(v)+.03))/(DRAWS+1))
            tests[key]=p
            hypotheses.append({'id':key,'kind':kind,'mean_difference':float(np.mean(v)) if v else None,'ci':ci,'p':p})
    adjusted=holm(tests)
    for h in hypotheses:
        h['holm_p']=adjusted[h['id']]
        h['success']=h['holm_p'] is not None and h['holm_p']<.05 and (h['kind']!='noninferiority' or (h['ci'] is not None and h['ci'][0]>-.03))
    with (root/'summary_tables.csv').open('x') as f:
        writer=csv.DictWriter(f,fieldnames=list(results[0]));writer.writeheader();writer.writerows(results)
    with (root/'statistics.json').open('x') as f:json.dump({'unit':'family','bootstrap_draws':DRAWS,'seed':SEED,'primary_hypotheses':hypotheses,'process_repeats_independent':False},f,indent=2)
    (root/'results_ledger.md').write_text('# Linked-cycle results\n\n'+ '\n'.join(f"- {h['id']}: {'supported' if h['success'] else 'not established'}; difference {h['mean_difference']}, CI {h['ci']}, Holm p {h['holm_p']}." for h in hypotheses)+'\n\nC5, canonical-store admission and source/session audit require their separate receipts.\n')

if __name__=='__main__':main()
