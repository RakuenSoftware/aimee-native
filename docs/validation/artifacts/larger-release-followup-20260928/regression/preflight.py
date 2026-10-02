"""CPU tokenizer preflight for frozen, source-backed coding regressions."""
import argparse
import hashlib
import json
from pathlib import Path
from transformers import AutoTokenizer

p = argparse.ArgumentParser()
p.add_argument('--inputs', required=True)
p.add_argument('--system', required=True)
p.add_argument('--output', required=True)
a = p.parse_args()
inputs = Path(a.inputs); rows = json.loads(inputs.read_text()); system = Path(a.system).read_text()
assert len(rows) == 6 and len({r['task']['instance_id'] for r in rows}) == 6
report = {'scope': 'Tokenizer fit only; no task execution or learning outcome',
          'input_sha256': hashlib.sha256(inputs.read_bytes()).hexdigest(),
          'context_tokens': 4096, 'output_tokens': 1536, 'reserve_tokens': 280,
          'input_budget': 2280, 'preparation_budget': 1024, 'profiles': {}}
for profile, folder in [('gemma26', 'gemma4-moe'), ('qwen27', 'model')]:
    model = Path('/opt/aimee-memory-lab') / folder
    tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
    results = []
    for row in rows:
        assert hashlib.sha256(row['fact'].encode()).hexdigest() == row['fact_sha256']
        task = row['task']; assert not {'patch', 'test_patch', 'FAIL_TO_PASS', 'PASS_TO_PASS'} & task.keys()
        question = 'Fix this issue:\n' + task['problem_statement']
        common = [{'role': 'system', 'content': system}, {'role': 'user', 'content': question}]
        text = [{'role': 'system', 'content': system + '\n\nAuthoritative memory:\n' + row['fact']}, common[1]]
        count = lambda messages: len(tokenizer.apply_chat_template(messages, tokenize=True,
            add_generation_prompt=True, enable_thinking=False))
        memory = 'Authoritative memory:\n' + row['fact']
        if profile == 'gemma26':
            memory = tokenizer.apply_chat_template([{'role': 'system', 'content': memory}],
                tokenize=False, add_generation_prompt=False, enable_thinking=False)
        memory_tokens = len(tokenizer.encode(memory, add_special_tokens=False))
        control, matched = count(common), count(text)
        results.append({'instance_id': task['instance_id'], 'control_and_native_prompt_tokens': control,
                        'text_prompt_tokens': matched, 'prepared_memory_tokens': memory_tokens,
                        'complete_issue_fits': max(control, matched) <= report['input_budget'],
                        'complete_memory_fits': memory_tokens <= report['preparation_budget']})
    report['profiles'][profile] = {'config_sha256': hashlib.sha256((model / 'config.json').read_bytes()).hexdigest(),
                                   'rows': results}
report['status'] = 'passed' if all(r['complete_issue_fits'] and r['complete_memory_fits']
    for profile in report['profiles'].values() for r in profile['rows']) else 'does_not_fit'
Path(a.output).write_text(json.dumps(report, indent=2) + '\n')
