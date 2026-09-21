"""Read-only audit of full-model traces; no model calls or scoring changes."""
import argparse
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--root', required=True)
p.add_argument('--cases', required=True)
p.add_argument('--records', required=True)
p.add_argument('--output', required=True)
a = p.parse_args()
root = Path(a.root)
cases = {c['id']: c for c in json.loads(Path(a.cases).read_text())}
records = {r['id']: r for r in json.loads(Path(a.records).read_text())['records']}
initial = [json.loads(s) for s in (root / 'results.jsonl').read_text().splitlines()]
fixed = [json.loads(s) for s in (root / 'native-fixed.jsonl').read_text().splitlines()]
none = {r['case']: r for r in initial if r['mode'] == 'none'}

def trace(row):
    return json.loads((root / 'traces' / (row['response']['id'] + '.json')).read_text())

audits = []
for run, rows in [('initial', initial), ('fixed', fixed)]:
    for row in rows:
        if row['mode'] != 'native':
            continue
        t = trace(row)
        control = trace(none[row['case']])
        assert t['prompt_token_ids'] == control['prompt_token_ids']
        assert t['generation_prompt'] == control['generation_prompt']
        assert t['memory_prompt_tokens'] == 0
        local_ids, private_ids, before_decode = set(), set(), set()
        response_events, empty_events = 0, 0
        for e in t['recall_events']:
            reply = e.get('aimee_response', {})
            facts = reply.get('facts', [])
            if 'restriction' in reply:
                assert reply['restriction']['namespace'] == 'aimee-published'
                assert set(reply['restriction']['ids']) <= {5, 6}
                response_events += bool(facts)
                empty_events += not facts
            for f in facts:
                ref = f['memory_ref']
                if ref['namespace'] == 'aimee-general-v1':
                    assert 'restriction' not in reply
                    canonical = records[ref['id']]
                    assert canonical['content'] == f['content']
                    assert canonical['revision'] == ref['revision']
                    local_ids.add(ref['id'])
                else:
                    assert ref['namespace'] == 'aimee-published'
                    assert ref['id'] in {'5', '6'}
                    private_ids.add(ref['id'])
            for ref in e.get('bank_memory_ids', []):
                assert ref['id'] != '999'
                if e['step'] == 0:
                    before_decode.add((ref['namespace'], ref['id']))
        expected = set(cases[row['case']]['memory_ids'])
        audits.append(dict(
            run=run, case=row['case'], prompt_identical_to_none=True,
            memory_prompt_tokens=0, local_general_ids=sorted(local_ids),
            expected_general_ids=sorted(expected),
            exact_general_set=local_ids == expected,
            expected_general_present_before_decode=all(
                ('aimee-general-v1', x) in before_decode for x in expected),
            personal_ids=sorted(private_ids),
            personal_present_before_decode=sorted(
                i for ns, i in before_decode if ns == 'aimee-published'),
            personal_not_requested=bool(private_ids) and not cases[row['case']].get('personal', False),
            remote_nonempty_events=response_events, remote_empty_events=empty_events,
            trace_sha256=hashlib.sha256((root / 'traces' / (row['response']['id'] + '.json')).read_bytes()).hexdigest(),
        ))
assert len(audits) == 68
assert all(x['exact_general_set'] for x in audits if x['run'] == 'fixed')
out = dict(native_runs_audited=len(audits), all_prompts_identical_to_none=True,
           all_general_payloads_match_canonical=True, general_from_remote=0,
           excluded_personal_ids_seen=0, cases=audits)
Path(a.output).write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps({k: v for k, v in out.items() if k != 'cases'}))
