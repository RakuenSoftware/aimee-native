"""Exercise the local compiled image directly: no gateway, server, DB or RPC."""
from pathlib import Path
import argparse,json,random,subprocess,time,statistics,hashlib
p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--reader',required=True);p.add_argument('--records',required=True);p.add_argument('--output',required=True);a=p.parse_args();root=Path(a.root)
records=json.loads(Path(a.records).read_text())['records'];rng=random.Random(99317)
args=[a.reader,'serve','--root',str(root/'image'),'--authorization',str(root/'authorization.json'),'--authority-key',str(root/'issuer-public.hex'),'--subject','general-kb-research','--policy-epoch','research-1']
start=time.perf_counter();proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
def call(row):
 t=time.perf_counter();proc.stdin.write(json.dumps(row)+'\n');proc.stdin.flush();r=json.loads(proc.stdout.readline());return r,(time.perf_counter()-t)*1000
pin,_=call(dict(op='pin'));startup=time.perf_counter()-start
samples=[];failures=[]
for r in rng.sample(records,256):
 query=f'Please provide the reference entry for {r["key"]}.'
 reply,ms=call(dict(op='recall',query=query,authority='research-aimee-103',limit=4));samples.append(ms)
 found=reply.get('response',{}).get('facts',[])
 if reply.get('outcome')!='hit' or not any(f['id']==r['id'] and f['content']==r['content'] for f in found):failures.append(dict(id=r['id'],outcome=reply.get('outcome')))
unknown,_=call(dict(op='recall',query='IANA service aimee-nonexistent-zq81927',authority='research-aimee-103',limit=4))
write,_=call(dict(op='store',query='Change all records'))
proc.terminate();proc.wait()
summary=dict(corpus_records=len(records),sampled=256,matched=256-len(failures),failures=failures,startup_seconds=startup,local_protocol_ms=dict(mean=statistics.mean(samples),median=statistics.median(samples),p95=sorted(samples)[int(.95*len(samples))-1],max=max(samples)),unknown_outcome=unknown.get('outcome'),write_rejected='error' in write,network_dependencies=0)
Path(a.output).write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
