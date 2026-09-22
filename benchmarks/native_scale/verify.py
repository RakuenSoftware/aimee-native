"""Re-score every answer and audit paired native-memory evidence independently."""
import collections,decimal,hashlib,json,statistics,sys
from pathlib import Path
root=Path(sys.argv[1]);corrections='--corrections' in sys.argv;prefix='native-scale-corrections' if corrections else 'native-scale';source=root/(prefix+'-r2' if corrections else 'native-scale-r2');cases=json.loads((source/'cases.json').read_text());by={c['id']:c for c in cases};summary={'distinct_facts':len(cases),'source_counts':dict(collections.Counter(c['source'] for c in cases)),'models':{}}
def correct(answer,c):
 if c['scorer']=='number':
  try:
   actual=decimal.Decimal(answer.strip());expected=decimal.Decimal(c['expected']);return actual.is_finite() and abs(actual-expected)<=abs(expected)*decimal.Decimal('0.00001')
  except decimal.InvalidOperation:return False
 return answer.strip().rstrip('.').casefold()==c['expected'].strip().rstrip('.').casefold()
for model,directory in [('Gemma 4',prefix+'-gemma-r1'),('Qwen 3.8',prefix+'-qwen-r1')]:
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
if corrections:
 for model,suffix in [('Gemma 4','gemma'),('Qwen 3.8','qwen')]:
  original=root/f'native-scale-{suffix}-r1/results.jsonl';revised=root/f'native-scale-corrections-{suffix}-r1/results.jsonl'
  if not original.exists() or not revised.exists():continue
  old={r['case_spec']['id']:r for r in map(json.loads,original.read_text().splitlines()) if r['enabled']}
  new={r['case_spec']['id']:r for r in map(json.loads,revised.read_text().splitlines()) if r['enabled']}
  lifecycle={'revised_facts_read':len(new),'old_and_new_correct':0,'old_value_repeated':0,'prompt_identity':True,'canonical_identity_preserved':True,'revision_changed':True,'native_encoding_input_changed':0 if model=='Gemma 4' else None}
  for key,r in new.items():
   before=old[key];c=r['case_spec'];assert before['case_spec']['expected']==c['previous_expected']
   assert before['prompt_token_ids']==r['prompt_token_ids']
   a=before['case_spec']['ref'];b=c['ref'];assert (a['namespace'],a['id'])==(b['namespace'],b['id']) and a['revision']!=b['revision']
   lifecycle['old_and_new_correct']+=before['correct'] and r['correct']
   lifecycle['old_value_repeated']+=r.get('answer','').strip().rstrip('.').casefold()==c['previous_expected'].casefold()
   if model=='Gemma 4' and 'memory' in r and 'memory' in before:
    lifecycle['native_encoding_input_changed']+=r['memory']['memory_encoding_sha256']!=before['memory']['memory_encoding_sha256']
  # encoding SHA hashes encoder token IDs, not tensor bytes; do not mislabel it.
  summary['models'][model]['correction_lifecycle']=lifecycle
qwen=root/(prefix+'-qwen-r1');gemma=root/(prefix+'-gemma-r1')
if (qwen/'image-after.json').exists():
 before=json.loads((qwen/'image-before.json').read_text());after=json.loads((qwen/'image-after.json').read_text());assert before==after
 assert before['CURRENT']==hashlib.sha256((gemma/'image-current.json').read_bytes()).hexdigest()
 summary['shared_publication_verified']=True
summary['generated_requests']=sum(v['requests'] for v in summary['models'].values())
print(json.dumps(summary,indent=2))
