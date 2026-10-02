"""Independently score paired general or procedural evaluations with trace audits."""
import collections,decimal,json,sys
from pathlib import Path
source=Path(sys.argv[1]);result=Path(sys.argv[2]);cases={c['id']:c for c in json.loads((source/'cases.json').read_text())}
pairs=collections.defaultdict(dict);violations=[];groups={};rows=0
for line in (result/'results.jsonl').open():
 r=json.loads(line);c=cases[r['case_spec']['id']];assert c==r['case_spec'];enabled=r['enabled'];assert enabled not in pairs[c['id']]
 answer=r.get('answer','').strip().rstrip('.')
 if c['scorer']=='exact':ok=r.get('answer','').strip()==c['expected']
 elif c['scorer'] in ('number','integer'):
  try:
   a=decimal.Decimal(r.get('answer','').strip());b=decimal.Decimal(c['expected']);ok=a.is_finite() and (a==b if c['scorer']=='integer' else abs(a-b)<=abs(b)*decimal.Decimal('0.00001'))
  except decimal.InvalidOperation:ok=False
 else:ok=answer.casefold()==c['expected'].strip().rstrip('.').casefold()
 assert bool(r['correct'])==ok;pairs[c['id']][enabled]=r;rows+=1
 assert r['memory_prompt_tokens']==0
 if r.get('error'):violations.append(dict(case=r['case'],error=r['error']))
 if 'parameter_versions_unchanged' in r:
  assert r['parameter_versions_unchanged'];assert r['main_cache_length']==r['expected_main_cache_length']
 if enabled and not r.get('error'):
  state=r.get('memory',r);assert state['native_reads']>0
  refs=[f.get('memory_ref') for e in state['recall_events'] for f in e.get('aimee_response',{}).get('facts',[])]
  assert c['ref'] in refs
for label in ['all']+sorted({c['domain'] for c in cases.values()}):
 selected=[c for c in cases.values() if label=='all' or c['domain']==label]
 out=dict(planned=len(selected),paired=0,disabled_correct=0,native_correct=0,recovered=0,regressed=0,disabled_unknown=0,native_unknown=0)
 for c in selected:
  pair=pairs[c['id']]
  if len(pair)!=2:continue
  assert pair[False]['prompt_token_ids']==pair[True]['prompt_token_ids'];out['paired']+=1
  for flag,key in [(False,'disabled'),(True,'native')]:
   out[key+'_correct']+=bool(pair[flag]['correct']);out[key+'_unknown']+=pair[flag].get('answer','').strip().rstrip('.').casefold()=='unknown'
  out['recovered']+=not pair[False]['correct'] and pair[True]['correct'];out['regressed']+=pair[False]['correct'] and not pair[True]['correct']
 groups[label]=out
print(json.dumps(dict(requests=rows,complete=rows==2*len(cases) and (result/'DONE').exists(),groups=groups,errors=violations),indent=2))
