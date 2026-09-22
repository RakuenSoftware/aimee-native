"""Audit actual old/new K/V hashes, source revisions and frozen parameters."""
import json,sys
from pathlib import Path
root=Path(sys.argv[1]);rows=[json.loads(line) for line in (root/'live-results.jsonl').read_text().splitlines()];pairs={}
for row in rows:
 assert 'error' not in row,row
 assert row['parameter_versions_unchanged'] and row['memory_prompt_tokens']==0
 assert row['main_cache_length']==row['expected_main_cache_length']
 assert len(row['native_tensors'])==48
 assert row['memory']['native_reads']>0
 assert row['correct']==(row['answer'].strip().rstrip('.').casefold()==row['expected'].casefold())
 key=row['case_spec']['id'];pairs.setdefault(key,{})[row['phase']]=row
out={'requests':len(rows),'facts':len(pairs),'old_correct':0,'new_correct':0,'old_and_new_correct':0,'native_bank_changed':0,'all_48_layer_banks_changed':0,'trained_parameter_versions_unchanged':True,'prompt_identity':True,'source_revision_changed':True,'memory_prompt_tokens':0,'by_fact':[]}
for key,pair in pairs.items():
 assert set(pair)=={'before','after'}
 before,after=pair['before'],pair['after'];assert before['prompt_token_ids']==after['prompt_token_ids'];assert before['expected']!=after['expected']
 a=before['memory']['aimee_response']['facts'][0]['memory_ref'];b=after['memory']['aimee_response']['facts'][0]['memory_ref'];assert a['id']==b['id'] and a['namespace']==b['namespace'] and a['revision']!=b['revision']
 changed=sum(any(before['native_tensors'][layer][kind]['sha256']!=after['native_tensors'][layer][kind]['sha256'] for kind in ['key','value']) for layer in before['native_tensors'])
 out['old_correct']+=before['correct'];out['new_correct']+=after['correct'];out['old_and_new_correct']+=before['correct'] and after['correct'];out['native_bank_changed']+=changed>0;out['all_48_layer_banks_changed']+=changed==48
 out['by_fact'].append(dict(id=key,changed_layers=changed,before=before['answer'],after=after['answer'],before_bytes=sum(t['bytes'] for bank in before['native_tensors'].values() for t in bank.values()),after_bytes=sum(t['bytes'] for bank in after['native_tensors'].values() for t in bank.values())))
assert out['requests']==250 and out['facts']==125
print(json.dumps(out,indent=2))
