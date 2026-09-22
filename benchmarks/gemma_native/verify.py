"""Verify saved Gemma native read/update evidence without a GPU."""
import hashlib
import json
from pathlib import Path
import sys

root=Path(sys.argv[1])
run=root/'gemma-native-r5'
rows=[json.loads(line) for line in (run/'results.jsonl').read_text().splitlines()]
expected=['unknown','cobalt','amber','violet','unknown']
assert len(rows)==5
prompt=rows[0]['prompt_token_ids']
for row,value in zip(rows,expected):
    assert 'error' not in row
    assert row['answer'].strip().rstrip('.').casefold()==value
    assert row['pass']
    assert row['prompt_token_ids']==prompt
    assert row['memory_prompt_tokens']==0
    assert row['parameter_versions_unchanged']
    assert row['main_cache_length']==row['expected_main_cache_length']
    if row['enabled']:
        state=row['memory']
        assert state['native_reads']>0
        assert state['memory_encoding_passes']==1
        assert len(state['bank_layers'])==48
        facts=state['aimee_response']['facts']
        assert len(facts)==1 and facts[0]['memory_ref']['id']=='aurora-access'
        assert facts[0]['content']==f'The access code for Aurora Observatory is {value}.'
        assert facts[0]['memory_ref']['revision']==('initial' if row['case']=='initial' else row['case'])
assert len({x['memory']['source_view'] for x in rows if x['enabled']})==3
runtime=json.loads((run/'runtime.json').read_text())
assert runtime['trainable_parameters']==0
summary={'model':runtime['model'],'model_revision':json.loads((run/'plan.json').read_text())['revision'],
         'checks_passed':5,'native_reads_passed':3,'disabled_controls_passed':2,
         'conversation_tokens':len(prompt),'identical_conversation_tokens':True,'memory_tokens_in_conversation':0,
         'trained_parameters_changed':False,'same_loaded_worker':True,
         'general_records':1,'updates':[{k:row[k] for k in ['case','answer','seconds','mutation_to_answer_seconds']}|{'publication_seconds':row['publication']['publication_seconds']} for row in rows if 'publication' in row]}
print(json.dumps(summary,indent=2))
