"""Independently verify complete frozen procedures in prepared native token records."""
import argparse
import hashlib
import json
from pathlib import Path
from transformers import AutoTokenizer

p = argparse.ArgumentParser()
p.add_argument('--profile', choices=['gemma26', 'qwen27'], required=True)
p.add_argument('--output', required=True)
a = p.parse_args()
root = Path('/opt/aimee-large-release-validation/regression')
source = root / 'frozen-inputs.json'
rows = json.loads(source.read_text())
state = json.loads((root / 'prepared-r2/preparation-status.json').read_text())['profiles'][a.profile]
assert state['status'] == 'prepared' and len(state['records']) == len(rows) == 6
model = Path('/opt/aimee-memory-lab') / ('gemma4-moe' if a.profile == 'gemma26' else 'model')
tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
checks = []
for row in rows:
    fact = row['fact']; digest = hashlib.sha256(fact.encode()).hexdigest()
    assert digest == row['fact_sha256']
    record = next(r for r in state['records'] if r['instance_id'] == row['task']['instance_id'])
    assert record['fact_sha256'] == digest
    bank = root / 'prepared-r2' / a.profile / record['publication']
    request = json.loads((bank / 'request.json').read_text())
    assert request['response']['facts'] == [{'content': fact}]
    memory = 'Authoritative memory:\n' + fact
    if a.profile == 'gemma26':
        memory = tokenizer.apply_chat_template([{'role': 'system', 'content': memory}],
            tokenize=False, add_generation_prompt=False, enable_thinking=False)
    expected = tokenizer.encode(memory, add_special_tokens=False)
    raw = (bank / 'index.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == record['index_sha256']
    index = json.loads(raw)
    assert index['records'][record['publication']]['tokens'] == expected, row['task']['instance_id']
    assert len(expected) == record['encoded_memory_tokens']
    checks.append({'instance_id': row['task']['instance_id'], 'fact_sha256': digest,
                   'publication': record['publication'], 'tokens': len(expected), 'all_token_ids_match': True})
report = {'status': 'passed', 'scope': __doc__, 'profile': a.profile,
          'inputs_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'records': checks}
output = Path(a.output)
assert not output.exists()
output.write_text(json.dumps(report, indent=2) + '\n')
