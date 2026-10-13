"""Evaluator-only post-hoc interpretation; never used for admission."""
import argparse,hashlib,json,re
from pathlib import Path

def candidates(raw):
    if not isinstance(raw,str):return []
    text=raw.strip()
    if text.startswith('```') and text.endswith('```'):text='\n'.join(text.splitlines()[1:-1])
    try:
        value=json.loads(text)
        def walk(v):
            if isinstance(v,str):yield v
            elif isinstance(v,dict):
                for child in v.values():yield from walk(child)
        found=list(walk(value))
    except json.JSONDecodeError:found=[text]
    result=[]
    for value in found:
        value=value.strip()
        for kind in ('noun','verb','adjective'):
            value=re.sub(r'\['+kind+r'\]', '{'+kind+'}',value,flags=re.I)
        if '\n' not in value and all(value.count('{'+kind+'}')==1 for kind in ('noun','verb','adjective')):result.append(value)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
    assert not a.out.exists()
    eval={x['family_id']:x for x in map(json.loads,(a.root/'fixture/evaluation/families.jsonl').open())}
    rows=[]
    for x in map(json.loads,(a.root/'acquisition-r1/acquisition_log.jsonl').open()):
        interpretations=candidates(x['rule_text']);ref=json.loads(eval[x['family_id']]['oracle_rule'])['output_template']
        status='exact_reference_template' if ref in interpretations else 'different_extractable_template' if interpretations else 'unresolved'
        rows.append({'family_id':x['family_id'],'attempt':x['attempt'],'status':status,'interpretations':interpretations,'training_matches':x['training_matches'],'admitted_candidate':x['admitted_candidate'],'raw_sha256':hashlib.sha256((x['rule_text'] or '').encode()).hexdigest()})
    from collections import Counter
    first=[x for x in rows if x['attempt']==1]
    a.out.write_text(json.dumps({'posthoc_only':True,'admission_unchanged':True,'counts':dict(Counter(x['status'] for x in rows)),'first_proposal_counts':dict(Counter(x['status'] for x in first)),'interpretation_limits':'Literal placeholder templates only; unresolved prose requires semantic inspection, not classification as wrong. Reference consulted after original scored campaign only. No response rescoring.','proposals':rows},indent=2))
if __name__=='__main__':main()
