#!/usr/bin/env python3
"""Four-arm, same-service native consumption measurement; raw samples retained."""
import argparse,json,random,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--pairs',type=int,default=10);p.add_argument('--url',default='http://127.0.0.1:18792');p.add_argument('--novel',action='store_true');a=p.parse_args()
query='Give the preferred drink of unit-b03646cbf4, then the home city of unit-121330aded. Separate with a semicolon.'
if a.novel:query='State the home city of unit-121330aded, followed by the preferred drink of unit-b03646cbf4. Separate with a semicolon.'
messages=[{'role':'system','content':'Answer using the available memory. Return only the requested value or values. If unknown, return unknown.'},{'role':'user','content':query}]
rng=random.Random(20260920)
arms=[('remote_uncached','remote',False),('remote_cached','remote',True),('local_first_uncached','local_first',False),('local_first_cached','local_first',True)]
with Path(a.output).open('w') as f:
 for pair in range(-2,a.pairs):
  order=arms.copy();rng.shuffle(order)
  for arm,backend,reuse in order:
   body={'messages':messages,'temperature':0,'max_tokens':48,'memory_backend':backend,'reuse_native_states':reuse}
   start=time.perf_counter()
   try:
    with urllib.request.urlopen(urllib.request.Request(a.url+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=120) as r:reply=json.load(r)
    row={'pair':pair,'warmup':pair<0,'arm':arm,'novel':a.novel,'seconds':time.perf_counter()-start,'response':reply}
   except Exception as e:row={'pair':pair,'arm':arm,'error':str(e)}
   f.write(json.dumps(row)+'\n');f.flush();print(json.dumps(row),flush=True)
