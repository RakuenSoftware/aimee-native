"""Recompute INT8 quality/coverage and verify every retained request trace."""
import argparse
import hashlib
import json
from pathlib import Path
from campaign import new_json
from hybrid_serving_profile import PROFILE, SYSTEM
from int8_consumption_validation import audit


def verify(root, suite):
    root = Path(root)
    report = json.loads((root / 'report.json').read_text())
    protocol_bytes = (root / 'protocol.json').read_bytes()
    protocol = json.loads(protocol_bytes)
    tasks = json.loads(Path(suite).read_text())['tasks']
    if (protocol['tasks'] != tasks or protocol['profile'] != PROFILE or protocol['system_context'] != SYSTEM
        or protocol['precision'] != 'rowwise INT8 research runtime'
        or protocol['schedule'] != 'preload-only' or protocol['turns'] != [0, 16, 48]
        or protocol['suite_sha256'] != hashlib.sha256(Path(suite).read_bytes()).hexdigest()
        or report['protocol_sha256'] != hashlib.sha256(protocol_bytes).hexdigest()):
        raise ValueError('frozen protocol identity mismatch')
    retained = protocol.get('retained_stage')
    if retained:
        old_bytes = (root / 'retained-protocol.json').read_bytes()
        if hashlib.sha256(old_bytes).hexdigest() != retained['protocol_sha256']:
            raise ValueError('retained protocol hash mismatch')
        old = json.loads(old_bytes)
        for key in ('tasks', 'profile', 'system_context', 'binary_sha256', 'reader_sha256', 'suite_sha256', 'model_config_sha256', 'revision', 'precision', 'schedule'):
            if old[key] != protocol[key]: raise ValueError('retained protocol identity mismatch: ' + key)
        if old['placement_sha256'] != retained['placement_sha256']:
            raise ValueError('retained placement identity mismatch')
        checks = [json.loads(line) for line in (root / 'resume-checks.jsonl').read_text().splitlines()]
        expected_checks = {(tasks[0]['id'], native, 0) for native in (True, False)}
        expected_checks.update((task['id'], native, 16) for task in tasks
                              if task['query'] == 'Which station code is reachable from Osreth outpost?'
                              for native in (True, False))
        if {(r['task'], r['native'], r['turns']) for r in checks} != expected_checks or len(checks) != len(expected_checks):
            raise ValueError('resume replay coverage mismatch')
        prior_rows = report['rows'][:retained['rows']]
        for replay in checks:
            matching = [r for r in prior_rows if (r['task'], r['native'], r['turns']) == (replay['task'], replay['native'], replay['turns'])]
            if len(matching) != 1 or any(matching[0][k] != replay[k] for k in ('answer', 'selected_refs', 'correct')):
                raise ValueError('resume replay answer/selection mismatch')
            data = (root / replay['trace']).read_bytes()
            if hashlib.sha256(data).hexdigest() != replay['trace_sha256'] or json.loads(data)['answer'].strip().rstrip('.') != replay['answer']:
                raise ValueError('resume replay trace mismatch')
    for phase in ('online', 'prepared'):
        argv = json.loads((root / (phase + '-invocation.json')).read_text())['argv']
        if '--int8' not in argv or '--enable-hybrid-native' not in argv:
            raise ValueError('wrong runtime profile')
    selection = json.loads((root / 'selection.json').read_text())
    if selection['system_context'] != SYSTEM or selection['consumption_profile'] != PROFILE:
        raise ValueError('source selection instruction identity mismatch')
    if set(selection['task_bundles']) != {task['id'] for task in tasks}:
        raise ValueError('source selection coverage mismatch')
    for row in report['rows']:
        path = Path(row['trace'])
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('unsafe trace path')
        data = (root / path).read_bytes()
        if hashlib.sha256(data).hexdigest() != row['trace_sha256']:
            raise ValueError('trace hash mismatch')
        trace = json.loads(data)
        facts = selection['bundle_facts'].get(selection['task_bundles'][row['task']], {'facts': []})['facts']
        if row['native']:
            expected_content = {(f['memory_ref']['namespace'], f['memory_ref']['id'], f['memory_ref']['revision'], f['content']) for f in facts}
            actual_content = {(f['memory_ref']['namespace'], f['memory_ref']['id'], f['memory_ref']['revision'], f['content'])
                              for event in trace.get('recall_events') or [] for f in event.get('aimee_response', {}).get('facts', [])}
            if actual_content != expected_content or trace['native_recurrent_state'] is not True:
                raise ValueError('native source content/profile mismatch')
        else:
            context = (SYSTEM + '\n\nAuthoritative memory:\n' + '\n'.join(f['content'] for f in facts)).strip()
            if (not trace['generation_prompt'].startswith('<|im_start|>system\n' + context + '<|im_end|>\n')
                or trace['native_recurrent_state'] is not None):
                raise ValueError('text control instruction/content mismatch')
        if trace['answer'].strip().rstrip('.') != row['answer']:
            raise ValueError('trace/answer mismatch')
        refs = sorted({tuple(f['memory_ref'][k] for k in ('namespace', 'id', 'revision'))
                       for event in trace.get('recall_events') or []
                       for f in event.get('aimee_response', {}).get('facts', [])})
        if refs != sorted(tuple(ref) for ref in row['selected_refs']):
            raise ValueError('trace/canonical selection mismatch')
        for name, trace_name in [('memory_encoding_passes', 'memory_encoding_passes'),
                                 ('system_context_sha256', 'native_system_context_sha256')]:
            if row[name] != trace[trace_name]: raise ValueError('trace metric mismatch')
    result = audit(report['rows'], tasks)
    for name in ('status', 'n', 'correct', 'groups', 'failures'):
        if result[name] != report[name]: raise ValueError('producer/audit mismatch: ' + name)
    lookup = {(r['task'], r['turns'], r['phase'], r['native']): r for r in report['rows']}
    pairs = []
    for task in tasks:
        for turns in (0, 16, 48):
            native = lookup[(task['id'], turns, 'online', True)]
            text = lookup[(task['id'], turns, 'online', False)]
            prepared = lookup[(task['id'], turns, 'prepared', True)]
            pairs.append({'task': task['id'], 'turns': turns, 'native_correct': native['correct'],
                          'text_correct': text['correct'], 'prepared_correct': prepared['correct'],
                          'online_prepared_equal': native['answer'] == prepared['answer']})
    result.update(trace_hashes_verified=len(report['rows']),
                  native_fail_text_pass=[p for p in pairs if not p['native_correct'] and p['text_correct']],
                  shared_native_text_failures=[p for p in pairs if not p['native_correct'] and not p['text_correct']],
                  online_prepared_disagreements=[p for p in pairs if not p['online_prepared_equal']],
                  report_sha256=hashlib.sha256((root / 'report.json').read_bytes()).hexdigest(),
                  binary_sha256=protocol['binary_sha256'], reader_sha256=protocol['reader_sha256'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('root', 'suite', 'output'): parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    result = verify(args.root, args.suite)
    new_json(Path(args.output), result)
    print(json.dumps(result, indent=2))
