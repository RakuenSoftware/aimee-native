import importlib.util,sys,pathlib,json,torch,time
sys.path.insert(0,'/opt/aimee-native-compiler')
r=pathlib.Path('/opt/aimee-memory-lab/fp32-reuse-diagnosis-20260928')
spec=importlib.util.spec_from_file_location('old',r/'original_gemma_compile.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
c=m.GemmaCompiler('/opt/aimee-memory-lab/gemma4',reuse_library='/opt/aimee-native-compiler/libaimee_prepare.so',compute_dtype='float32');c.load()
b=m.GemmaCompiler('/opt/aimee-memory-lab/gemma4',compute_dtype='float32');b.model=c.model
identity={'recipient':'synthetic/user-a','authorized_view':'synthetic/view-a','model_revision':'gemma-fixture','runtime_profile':'cpu-float32','encoding_revision':'joint-negative-float32','position_policy':'negative-complete-set'}
facts=['The verification vault code is 53728.','The verification project is named Willow.','The verification drink is chamomile tea.']
def request(facts,rev):return {'identity':dict(identity,records=[{'namespace':'fixture','id':str(i),'revision':str(rev)} for i in range(len(facts))]),'response':{'facts':[{'content':f} for f in facts]}}
c.encode(request(facts,0));changed=facts[:-1]+['The verification drink is peppermint tea.'];tokens,fresh=b.encode(request(changed,1));_,reused=c.encode(request(changed,1));prefix=c.last_metrics['reused_prefix_tokens'];rows=[]
for layer in fresh:
 for kind,x,y in zip(['key','value'],fresh[layer],reused[layer]):
  d=(x.float()-y.float()).abs();mask=x!=y
  rows.append({'layer':layer,'kind':kind,'elements':x.numel(),'different':int(mask.sum()),'prefix_different':int(mask[:,:,:prefix,:].sum()),'suffix_different':int(mask[:,:,prefix:,:].sum()),'max_absolute_difference':float(d.max()),'mean_absolute_difference':float(d.mean())})
report={'status':'complete','scope':'Quantify previously failed partial-prefix export, not a tolerance-based acceptance','tokens':len(tokens),'prefix':prefix,'rows':rows}
(r/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps({'different':sum(x['different'] for x in rows),'prefix_different':sum(x['prefix_different'] for x in rows),'max_absolute_difference':max(x['max_absolute_difference'] for x in rows)}),flush=True)
