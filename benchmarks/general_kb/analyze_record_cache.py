"""Audit paired prompts, admitted banks and actual encoding work from raw traces."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args()
rows=[json.loads(line) for line in (a.root/'results.jsonl').read_text().splitlines()]
assert len(rows)==42
by_mode={mode:[r for r in rows if r['mode']==mode] for mode in ['bank','record']}
comparisons=[]
for old,new in zip(by_mode['bank'],by_mode['record']):
 assert (old['case'],old['reuse'])==(new['case'],new['reuse'])
 assert old['prompt_token_ids']==new['prompt_token_ids']
 traces=[json.loads((a.root/'traces'/(r['id']+'.json')).read_text()) for r in [old,new]]
 for t in traces:assert t['memory_prompt_tokens']==0 and t['memory_before_prompt']
 events=[[e for e in t['recall_events'] if 'bank_memory_ids' in e] for t in traces]
 before=events[0][0]['bank_memory_ids'];after=events[1][0]['bank_memory_ids']
 baseline_tokens=sum(e['memory_encoding_tokens'] for e in events[0] if e['status']=='bank_updated')
 record_tokens=sum(e.get('tokens_encoded',0) for e in events[1])
 comparisons.append(dict(case=old['case'],reuse=old['reuse'],same_preload=before==after,same_final=old['bank']==new['bank'],bank_answer=old['answer'],record_answer=new['answer'],bank_pass=old['pass_'],record_pass=new['pass_'],bank_encodings=old['encodings'],record_encodings=new['encodings'],bank_tokens_encoded=baseline_tokens,record_tokens_encoded=record_tokens,bank_encoding_ms=old['encoding_ms'],record_encoding_ms=new['encoding_ms'],record_cache_hits=new['record_cache_hits'],record_working_set_hits=new['record_working_set_hits']))
(a.root/'comparison.json').write_text(json.dumps(comparisons,indent=2)+'\n')
print(json.dumps(comparisons,indent=2))
