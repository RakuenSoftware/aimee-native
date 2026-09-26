"""Exact CPU comparison against the deployed one-shot encoder; synthetic records."""
import argparse,hashlib,importlib.util,json,pathlib,sys,time
import torch
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--source',required=True);p.add_argument('--library',required=True);p.add_argument('--baseline-source',default='/opt/aimee-native-compiler/gemma_compile.py');p.add_argument('--model',default='/opt/aimee-memory-lab/gemma4');a=p.parse_args()
r=pathlib.Path(a.output);r.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,a.source)
from gemma_compile import GemmaCompiler
old_spec=importlib.util.spec_from_file_location('baseline_gemma',a.baseline_source);old=importlib.util.module_from_spec(old_spec);old_spec.loader.exec_module(old)
c=GemmaCompiler(a.model,reuse_library=a.library);c.load();baseline=old.GemmaCompiler(a.model);baseline.model=c.model
identity={'recipient':'synthetic/user-a','authorized_view':'synthetic/view-a','model_revision':'gemma-fixture','runtime_profile':'cpu-bf16','encoding_revision':'joint-negative-v1','position_policy':'negative-complete-set'}
base=['The verification vault code is 53728.','The verification project is named Willow.','The verification drink is chamomile tea.']
changed=base[:-1]+['The verification drink is peppermint tea.']
cases=[('initial',base,{}),('last-record-change',changed,{}),('identical-content-new-revision',changed,{}),('length-change',base[:-1]+['The verification drink is very strong black coffee.'],{}),('reorder',list(reversed(base)),{}),('recipient-change',list(reversed(base)),{'recipient':'synthetic/user-b'}),('view-change',list(reversed(base)),{'recipient':'synthetic/user-b','authorized_view':'synthetic/view-b'})]
wide=[f'The access code for unit {i:03d} is {20000+i}.' for i in range(32)]
cases += [('wide-initial',wide,{}),('wide-tail-change',wide[:-1]+['The access code for unit 031 is 91827.'],{})]
report={'status':'running','scope':'synthetic exact computation reuse; no authority claim','rows':[]}
def digest(banks):
 h=hashlib.sha256()
 for _,pair in sorted(banks.items()):
  for t in pair:h.update(t.contiguous().view(torch.uint8).numpy().tobytes())
 return h.hexdigest()
for num,(label,facts,override) in enumerate(cases):
 request={'identity':dict(identity,**override,records=[{'namespace':'fixture','id':str(i),'revision':str(num)} for i in range(len(facts))]),'response':{'facts':[{'content':s} for s in facts]}}
 start=time.perf_counter();bt,bb=baseline.encode(request);btiming=time.perf_counter()-start
 start=time.perf_counter();nt,nb=c.encode(request);ntiming=time.perf_counter()-start
 exact=bt==nt and all(torch.equal(x,y) for i in bb for x,y in zip(bb[i],nb[i]))
 row={'case':label,'records':len(facts),'baseline_seconds':btiming,'optimized_seconds':ntiming,'exact':exact,'baseline_sha256':digest(bb),'optimized_sha256':digest(nb),**c.last_metrics};report['rows'].append(row)
 (r/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(row),flush=True);assert exact,label
 if label in ['recipient-change','view-change','length-change']:assert c.last_metrics['reused_prefix_tokens']==0
 del bb,nb
report['status']='passed';(r/'report.json').write_text(json.dumps(report,indent=2)+'\n')
