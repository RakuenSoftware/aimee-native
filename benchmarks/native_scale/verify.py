"""Re-score every answer and audit paired native-memory evidence independently."""
import collections,decimal,hashlib,json,statistics,sys
from pathlib import Path
root=Path(sys.argv[1]);source=root/'native-scale-r2';cases=json.loads((source/'cases.json').read_text());by={c['id']:c for c in cases};summary={'distinct_facts':len(cases),'source_counts':dict(collections.Counter(c['source'] for c in cases)),'models':{}}
def correct(answer,c):
 if c['scorer']=='number':
  try:
   actual=decimal.Decimal(answer.strip());expected=decimal.Decimal(c['expected']);return actual.is_finite() and abs(actual-expected)<=abs(expected)*decimal.Decimal('0.00001')
  except decimal.InvalidOperation:return False
 return answer.strip().rstrip('.').casefold()==c['expected'].strip().rstrip('.').casefold()
for model,directory in [('Gemma 4','native-scale-gemma-r1'),('Qwen 3.8','native-scale-qwen-r1')]:
 path=root/directory/'results.jsonl'
 if not path.exists():continue
 rows=[json.loads(line) for line in path.read_text().splitlines()];pairs=collections.defaultdict(dict);errors=[];violations=[];selected=0;native_count=0
 for row in rows:
  c=by[row['case_spec']['id']];assert c==row['case_spec']
  enabled=row['enabled'];assert enabled not in pairs[c['id']];pairs[c['id']][enabled]=row
  assert bool(row['correct'])==correct(row.get('answer',''),c)
  assert row['memory_prompt_tokens']==0
  if 'error' in row:errors.append({'case':row['case'],'error':row['error']});continue
  if model=='Gemma 4':
   assert row['parameter_versions_unchanged']
   assert row['main_cache_length']==row['expected_main_cache_length']
  if enabled:
   native_count+=1;memory=row.get('memory',row)
   if memory.get('native_reads',0)==0:violations.append({'case':row['case'],'issue':'zero native reads'})
   events=memory.get('recall_events') or [];refs=[f.get('memory_ref') for e in events for f in e.get('aimee_response',{}).get('facts',[])]
   if c['ref'] in refs:selected+=1
   else:violations.append({'case':row['case'],'issue':'expected revision not selected'})
 groups={}
 for label in ['personal','general']+sorted({c['domain'] for c in cases}):
  chosen=[c for c in cases if c['source']==label or c['domain']==label];stats={'facts':len(chosen),'disabled_n':0,'disabled_correct':0,'native_n':0,'native_correct':0,'recovered':0,'regressed':0,'disabled_unknown':0,'native_unknown':0}
  for c in chosen:
   pair=pairs.get(c['id'],{})
   for flag,name in [(False,'disabled'),(True,'native')]:
    if flag in pair:
     r=pair[flag];stats[name+'_n']+=1;stats[name+'_correct']+=bool(r['correct']);stats[name+'_unknown']+=r.get('answer','').strip().rstrip('.').casefold()=='unknown'
   if len(pair)==2:
    assert pair[False]['prompt_token_ids']==pair[True]['prompt_token_ids']
    stats['recovered']+=not pair[False]['correct'] and pair[True]['correct'];stats['regressed']+=pair[False]['correct'] and not pair[True]['correct']
  groups[label]=stats
 summary['models'][model]={'requests':len(rows),'complete':len(rows)==2*len(cases),'groups':groups,'errors':errors,'native_successful_requests':native_count,'expected_revision_selected':selected,'violations':violations}
summary['generated_requests']=sum(v['requests'] for v in summary['models'].values())
print(json.dumps(summary,indent=2))
