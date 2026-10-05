"""Research-only fitted partition router. Its output is a candidate hint.

The trusted memory owner must resolve/authorize candidates and enforce record,
position and byte budgets. This module cannot return record content or grant
eligibility. No weights or trained routing enter the production adapter.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time

CONTRACT = {'model_revision','representation','layer','pooling','position','width'}


def contract(value):
    if not isinstance(value,dict) or set(value)!=CONTRACT:
        raise ValueError('exact representation contract required')
    if type(value['width']) is not int or value['width']<1 or type(value['layer']) is not int or value['layer']<0:
        raise ValueError('invalid representation geometry')
    if any(not isinstance(value[k],str) or not value[k] for k in CONTRACT-{'width','layer'}):
        raise ValueError('representation identities required')
    return value


def normalize(value,width):
    if not isinstance(value,list) or len(value)!=width:
        raise ValueError('feature width differs')
    if any(type(x) not in (float,int) or not math.isfinite(x) for x in value):
        raise ValueError('finite numeric features required')
    length=math.sqrt(sum(x*x for x in value))
    if not math.isfinite(length) or length==0:
        raise ValueError('nonzero bounded features required')
    return [x/length for x in value]


def fit(samples,representation):
    representation=contract(representation)
    groups={}
    for sample in samples:
        partition=sample['partition']
        if not isinstance(partition,str) or not partition:
            raise ValueError('partition identity required')
        vector=normalize(sample['features'],representation['width'])
        groups.setdefault(partition,[]).append(vector)
    if not groups:raise ValueError('development examples required')
    centers={}
    for partition,rows in sorted(groups.items()):
        centers[partition]=normalize([sum(col)/len(rows) for col in zip(*rows)],representation['width'])
    return {'schema':'native-partition-router-v1','contract':dict(representation),
            'method':'cosine-development-centroid','centers':centers}


def route(router,features,representation,available_partitions,*,budget=2,min_score=.1,min_margin=0.):
    """available_partitions is a trusted current-view hint, never caller permission."""
    contract(representation)
    if type(budget) is not int or budget<1:
        raise ValueError('positive candidate-partition budget required')
    if not isinstance(available_partitions,(set,list,tuple)) or any(not isinstance(p,str) or not p for p in available_partitions):
        raise ValueError('trusted partition names required')
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in (min_score,min_margin)) or not -1<=min_score<=1 or not 0<=min_margin<=2:
        raise ValueError('invalid confidence thresholds')
    if router.get('schema')!='native-partition-router-v1' or router.get('contract')!=representation:
        return {'partitions':[],'fallback_required':True,'reason':'representation_mismatch'}
    query=normalize(features,representation['width'])
    scores=[]
    for name,center in router['centers'].items():
        if name in available_partitions:
            c=normalize(center,representation['width'])
            scores.append((sum(x*y for x,y in zip(query,c)),name))
    scores.sort(key=lambda row:(-row[0],row[1]))
    if not scores:return {'partitions':[],'fallback_required':True,'reason':'no_current_candidates'}
    if scores[0][0]<min_score or (len(scores)>1 and scores[0][0]-scores[1][0]<min_margin):
        return {'partitions':[],'fallback_required':True,'reason':'uncertain'}
    return {'partitions':[name for score,name in scores[:budget]],
            'fallback_required':False,'reason':'candidate_hint'}


def evaluate(data,budget,min_score,min_margin):
    representation=contract(data['contract'])
    train=[s for s in data['samples'] if s['split']=='development']
    test=[s for s in data['samples'] if s['split']=='heldout']
    if not train or not test:raise ValueError('development and heldout examples required')
    for s in data['samples']:
        if s['split'] not in ('development','heldout') or not isinstance(s['family'],str) or not s['family']:
            raise ValueError('explicit family and split required')
    if {s['family'] for s in train}&{s['family'] for s in test}:
        raise ValueError('family leakage across development and heldout')
    router=fit(train,representation);rows=[]
    for s in test:
        start=time.perf_counter_ns()
        hint=route(router,s['features'],representation,data['available_partitions'],budget=budget,min_score=min_score,min_margin=min_margin)
        rows.append({'family':s['family'],'expected_partition':s['partition'],
                     'candidate_hit':s['partition'] in hint['partitions'],
                     'routing_ns':time.perf_counter_ns()-start,**hint})
    return {'schema':'native-routing-evaluation-v1','contract':representation,
            'budget':budget,'min_score':min_score,'min_margin':min_margin,
            'training_examples':len(train),'heldout_examples':len(test),
            'candidate_hits':sum(r['candidate_hit'] for r in rows),
            'fallbacks':sum(r['fallback_required'] for r in rows),
            'scope':'routing only; no native-consumption or final-answer claim',
            'rows':rows},router


def private_new(path,value):
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as out:
        json.dump(value,out,indent=2,allow_nan=False);out.write('\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('dataset');p.add_argument('--output',required=True)
    p.add_argument('--router-output',required=True)
    p.add_argument('--budget',type=int,default=2);p.add_argument('--min-score',type=float,default=.1)
    p.add_argument('--min-margin',type=float,default=0.)
    args=p.parse_args();raw=Path(args.dataset).read_bytes()
    report,router=evaluate(json.loads(raw),args.budget,args.min_score,args.min_margin)
    report['dataset_sha256']=hashlib.sha256(raw).hexdigest()
    private_new(args.router_output,router);private_new(args.output,report)
