"""Audit every changed cue and sample the actual Rust/Go lookup path."""
import collections,importlib.util,json,random,statistics,subprocess,time
from pathlib import Path
b=Path('/opt/aimee-qwen-rust');root=b/'kb-cue-fix-20260921'
spec=importlib.util.spec_from_file_location('cues',b/'cues-v2.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
def groups(path):
    result=collections.defaultdict(set)
    for row in json.loads(path.read_text()):
        r=row['ref'];result[c.normalize_cue(row['cue'])].add((r['namespace'],r['id'],r['revision']))
    return result
old=groups(b/'general-v2-cues.json');new=groups(root/'cues.json')
# Numeric rendering changed NIST revisions yesterday. Compare identities here;
# the compiled-image reader validates revisions on every returned object.
def ids(refs):return {(ns,id) for ns,id,revision in refs}
assert set(old)==set(new), 'unexpected address loss/addition'
for cue,refs in old.items():
    assert ids(new[cue]) <= ids(refs),cue
    if len(refs)==1:assert ids(new[cue])==ids(refs),cue
changed=[cue for cue in old if ids(old[cue])!=ids(new[cue])]
resolved=[cue for cue in changed if len(new[cue])==1]
ambiguous=[cue for cue in new if len(new[cue])>1]
unique=[cue for cue in new if len(new[cue])==1]
summary=dict(addresses=len(new),old_unique=sum(len(v)==1 for v in old.values()),new_unique=len(unique),
    old_ambiguous=sum(len(v)>1 for v in old.values()),new_ambiguous=len(ambiguous),changed_addresses=len(changed),
    resolved_addresses=len(resolved),previous_unique_mappings_unchanged=True)
args=['runuser','-u','aimee-auth-native','--','env','LD_LIBRARY_PATH=/opt/aimee-native-p0-training/lib/python3.13/site-packages/torch/lib',
    str(b/'target/release/aimee-qwen'),'read-check','--memory-image',str(root/'image'),'--image-reader',str(b/'aimee-memory-image'),
    '--read-authority','test','--read-gateway',str(root/'ABSENT_GATEWAY')]
p=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,cwd=root)
def call(op,query=None):
    request=dict(op=op)
    if query:request.update(query=query,limit=4)
    start=time.perf_counter_ns();p.stdin.write(json.dumps(request)+'\n');p.stdin.flush();line=p.stdout.readline();assert line
    return json.loads(line)['result'],(time.perf_counter_ns()-start)/1e6
start=time.perf_counter();reply,_=call('begin');assert 'error' not in reply,reply
summary['startup_seconds']=time.perf_counter()-start
results=[]
sets=[('resolved',resolved),('unique_sample',random.Random(310).sample(unique,min(2048,len(unique)))),
      ('ambiguous_sample',random.Random(310).sample(ambiguous,min(512,len(ambiguous))))]
for mode,addresses in sets:
    for cue in addresses:
        reply,ms=call('native_search','Please look up '+cue+'.')
        actual={(f['memory_ref']['namespace'],f['memory_ref']['id'],f['memory_ref']['revision']) for f in reply.get('facts',[])}
        passed=actual==new[cue] if len(new[cue])==1 else 'error' in reply
        results.append(dict(mode=mode,cue=cue,pass_=passed,ms=ms,expected=sorted(new[cue]),actual=sorted(actual)))
p.stdin.close();p.wait(timeout=10)
for mode,_ in sets:
    rr=[r for r in results if r['mode']==mode];times=sorted(r['ms'] for r in rr)
    summary[mode]=dict(total=len(rr),passed=sum(r['pass_'] for r in rr),median_ms=statistics.median(times),p95_ms=times[int(.95*len(times))-1])
(root/'lookup-results.json').write_text(json.dumps(dict(summary=summary,results=results),indent=2)+'\n')
print(json.dumps(summary,indent=2),flush=True)
assert all(r['pass_'] for r in results)
