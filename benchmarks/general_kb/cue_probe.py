"""Exercise actual Rust/local-reader routing with approved public alternate names."""
import json,os,random,statistics,subprocess,time,re
from collections import defaultdict
from pathlib import Path
b=Path('/opt/aimee-qwen-rust');root=b/'kb-followup-20260920'
cues=json.loads((b/'general-v2-cues.json').read_text());groups=defaultdict(set)
def norm(x):return ' '.join(w.strip('.') for w in re.findall(r'[\w\-/.]+',x.lower()) if w.strip('.'))
for c in cues:groups[norm(c['cue'])].add(c['ref']['id'])
unique=[c for c in cues if len(groups[norm(c['cue'])])==1]
ambiguous=[c for c in cues if len(groups[norm(c['cue'])])>1]
args=['runuser','-u','aimee-auth-native','--','env','LD_LIBRARY_PATH=/opt/aimee-native-p0-training/lib/python3.13/site-packages/torch/lib',str(b/'target/release/aimee-qwen'),'read-check','--memory-image',str(root/'image'),'--image-reader',str(b/'aimee-memory-image'),'--read-authority','test','--read-gateway',str(root/'ABSENT_GATEWAY')]
p=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,cwd=root)
def call(op,query=None):
 q={'op':op}
 if query:q.update(query=query,limit=4)
 t=time.perf_counter_ns();p.stdin.write(json.dumps(q)+'\n');p.stdin.flush();raw=p.stdout.readline();assert raw
 return json.loads(raw)['result'],(time.perf_counter_ns()-t)/1e6
start=time.perf_counter();r,_=call('begin');assert 'error' not in r,r;startup=time.perf_counter()-start
results=[]
for mode,pop in [('unique',unique),('ambiguous',ambiguous)]:
 sample=random.Random(310).sample(pop,min(2048 if mode=='unique' else 256,len(pop)))
 for c in sample:
  result,ms=call('native_search','Please look up '+c['cue']+'.')
  ids={f['memory_ref']['id'] for f in result.get('facts',[])}
  ok=ids=={c['ref']['id']} if mode=='unique' else 'error' in result
  results.append(dict(mode=mode,cue=c['cue'],expected=c['ref']['id'],ids=sorted(ids),pass_=ok,ms=ms))
p.stdin.close();p.wait(timeout=10)
summary=dict(cues=len(cues),unique_addresses=sum(len(v)==1 for v in groups.values()),ambiguous_addresses=sum(len(v)>1 for v in groups.values()),startup_seconds=startup)
for mode in ['unique','ambiguous']:
 rows=[r for r in results if r['mode']==mode];times=sorted(r['ms'] for r in rows)
 summary[mode]=dict(total=len(rows),correct=sum(r['pass_'] for r in rows),median_ms=statistics.median(times),p95_ms=times[int(.95*len(times))-1])
(root/'cue-results.json').write_text(json.dumps(dict(summary=summary,results=results),indent=2)+'\n')
print(json.dumps(summary),flush=True)
