#!/usr/bin/env python3
"""Drive configured real serving backends in randomized matched pairs."""
import argparse,json,random,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:18792');p.add_argument('--output',required=True);p.add_argument('--pairs',type=int,default=10);args=p.parse_args()
messages=[{'role':'system','content':'Answer using the available memory. Return only the requested value or values. If unknown, return unknown.'},{'role':'user','content':'Give the preferred drink of unit-b03646cbf4, then the home city of unit-121330aded. Separate with a semicolon.'}]
out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
rng=random.Random(20260920)
with out.open('w') as f:
    for pair in range(-2,args.pairs):
        order=['local','remote'];rng.shuffle(order)
        for backend in order:
            request={'messages':messages,'temperature':0,'max_tokens':48,'memory_backend':backend}
            start=time.perf_counter()
            try:
                with urllib.request.urlopen(urllib.request.Request(args.url+'/v1/chat/completions',data=json.dumps(request).encode(),headers={'Content-Type':'application/json'}),timeout=120) as response:
                    result=json.load(response)
                record={'pair':pair,'warmup':pair<0,'backend':backend,'seconds':time.perf_counter()-start,'response':result}
            except Exception as e:
                record={'pair':pair,'backend':backend,'error':str(e)}
            f.write(json.dumps(record)+'\n');f.flush();print(json.dumps(record),flush=True)
