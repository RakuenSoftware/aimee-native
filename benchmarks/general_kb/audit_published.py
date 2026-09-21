"""Audit the published-reader model run against the preserved guarded baseline."""
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

base = Path('/opt/aimee-qwen-rust')
root = base/'published-kb-live'
old = base/'general-kb-live'
rows = [json.loads(s) for s in (root/'results.jsonl').read_text().splitlines()]
previous = {r['case']: r for r in map(json.loads,(old/'native-fixed.jsonl').read_text().splitlines())}
cases = {r['id']: r for r in json.loads((base/'general-cases.json').read_text())}
canonical = {r['id']: r for r in json.loads((base/'records.json').read_text())['records']}
assert len(rows) == len(previous) == len(cases) == 34
audit = []
for r in rows:
    assert r['status'] == 200
    trace_path = root/'traces'/(r['response']['id']+'.json')
    t = json.loads(trace_path.read_text())
    prior = previous[r['case']]
    control = json.loads((old/'traces'/(prior['response']['id']+'.json')).read_text())
    assert t['memory_prompt_tokens'] == 0
    assert t['prompt_token_ids'] == control['prompt_token_ids']
    general, personal = set(), set()
    for e in t['recall_events']:
        reply = e.get('aimee_response', {})
        for f in reply.get('facts', []):
            ref = f['memory_ref']
            if ref['namespace'] == 'aimee-general-v1':
                assert 'restriction' not in reply
                assert f['content'] == canonical[ref['id']]['content']
                assert ref['revision'] == canonical[ref['id']]['revision']
                general.add(ref['id'])
            else:
                assert ref['namespace'] == 'aimee-published' and ref['id'] in {'5','6'}
                personal.add(ref['id'])
    assert general == set(cases[r['case']]['memory_ids'])
    audit.append(dict(case=r['case'],correct=r['pass_'],answer_unchanged=r['answer']==prior['answer'],
        general_ids=sorted(general),personal_ids=sorted(personal),
        trace_sha256=hashlib.sha256(trace_path.read_bytes()).hexdigest()))
assert not (root/'image/AUTHORIZATION.json').exists()
subprocess.run(['runuser','-u','aimee-auth-native','--','test','!','-r',str(root/'authorization.json')],check=True)
launch = subprocess.check_output(['systemctl','show','aimee-rust-qwen','--property=ExecStart','--value'],text=True)
assert '--authorization' not in launch and '--authority-key' not in launch
summary = dict(requests=len(rows),correct=sum(r['pass_'] for r in rows),
    all_general_facts_local=True,all_main_prompts_identical=True,memory_prompt_tokens=0,
    grant_files_in_image=0,model_can_read_gateway_grant=False,
    model_launch_has_local_authorization=False,model_launch=launch.strip(),
    end_to_end_seconds=dict(median=statistics.median(r['seconds'] for r in rows),
        mean=statistics.mean(r['seconds'] for r in rows),total=sum(r['seconds'] for r in rows)),
    failures=[dict(case=r['case'],answer=r['answer'],expected=r['expected']) for r in rows if not r['pass_']],
    cases=audit,
    runtime_hashes={name:hashlib.sha256((base/path).read_bytes()).hexdigest() for name,path in
        [('rust','target/release/aimee-qwen'),('reader','aimee-memory-image'),('corpus','records.json')]})
(root/'audit.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ['cases','model_launch']}))
