#!/usr/bin/env python3
"""Public synthetic read fixture, not an authorization implementation.

Never use this reader with real memory. It supports the research read protocol
only, returns no remote fallback, and checks its immutable file view every call.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

p=argparse.ArgumentParser();p.add_argument('operation',choices=['serve-published'])
p.add_argument('--root',required=True);args=p.parse_args()
path=Path(args.root)/'fixture.json';raw=path.read_bytes();view=hashlib.sha256(raw).hexdigest()
data=json.loads(raw)
by_id={f['memory_ref']['id']:f for f in data['facts']}
index={}
for fact in data['facts']:
    for alias in fact['aliases']:
        index.setdefault(alias.lower(),[]).append(fact)

def handle(req):
    if hashlib.sha256(path.read_bytes()).hexdigest()!=view:return {'error':'fixture changed'}
    if req['op'] in ('pin','check'):return {'publication':view,'view':view}
    if req['op']=='retain':return {'view':view,'retained':[False]*len(req['proofs'])}
    if req['op']=='recall':
        selected={}
        # Explicit owner-side oracle control for consumption experiments only.
        # Every hinted record must exist in this immutable public fixture view.
        hint_path=Path(args.root)/'oracle-hint.json'
        if hint_path.exists():
            hint=json.loads(hint_path.read_text())
            if set(hint)!={'ids'} or not isinstance(hint['ids'],list):raise ValueError('invalid oracle hint')
            for id in hint['ids']:
                fact=by_id[id];ref=fact['memory_ref'];selected[(ref['namespace'],id)]=fact
            facts=list(selected.values())
            if len(facts)>req['limit']:raise ValueError('oracle exceeds candidate budget')
            return {'view':view,'outcome':'hit','response':{'facts':[{'content':f['content'],'memory_ref':f['memory_ref']} for f in facts]}}
        for token in re.findall(r'[\w-]+',req['query'].lower()):
            for fact in index.get(token,[]):
                ref=fact['memory_ref'];selected[(ref['namespace'],ref['id'])]=fact
        facts=sorted(selected.values(),key=lambda f:f['memory_ref']['id'])[:req['limit']]
        return {'view':view,'outcome':'hit','response':{'facts':[{'content':f['content'],'memory_ref':f['memory_ref']} for f in facts]}}
    return {'error':'unsupported fixture operation'}

for line in sys.stdin:
    try:reply=handle(json.loads(line))
    except Exception:reply={'error':'fixture request invalid'}
    print(json.dumps(reply),flush=True)
