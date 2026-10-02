"""Summarize saved coding evidence without treating empty patches as test failures."""
import argparse
import json
from pathlib import Path
import statistics

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('root', type=Path)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
state = json.loads((a.root / 'status.json').read_text())
report = {'status': state['status'], 'completed_attempts': len(state['results']),
          'target_attempts': state['target_attempts'], 'scope': state['scope'],
          'arms': {}, 'pairs': {}, 'initial_prompt_tokens': {}, 'patch_files': {}, 'official_test_counts': {}}
for arm in ('control', 'text', 'native', 'native-repeat'):
    rows = [r for r in state['results'] if r['arm'] == arm]
    report['arms'][arm] = {
        'completed': len(rows), 'resolved': sum(r['resolved'] is True for r in rows),
        'empty_submissions': sum(r['grade_status'] == 'empty_prediction' for r in rows),
        'graded_failures': sum(r['grade_status'] == 'graded' and r['resolved'] is False for r in rows),
        'infrastructure_errors': sum(r['resolved'] is None for r in rows),
        'prompt_tokens': sum(r.get('tokens', {}).get('prompt_tokens', 0) for r in rows),
        'completion_tokens': sum(r.get('tokens', {}).get('completion_tokens', 0) for r in rows),
        'model_calls': sum(r.get('metered_calls', 0) for r in rows),
        'agent_seconds': sum(r['agent_seconds'] for r in rows),
        'median_agent_seconds': statistics.median(r['agent_seconds'] for r in rows) if rows else None,
    }
for row in state['results']:
    iid, arm = row['instance_id'], row['arm']
    report['pairs'].setdefault(iid, {})[arm] = {
        k: row.get(k) for k in ('resolved', 'grade_status', 'exit_status', 'steps', 'agent_seconds', 'tokens')}
    report['patch_files'].setdefault(iid, {})[arm] = [line[6:] for line in row.get('model_patch', '').splitlines() if line.startswith('+++ b/')]
    trajectory = a.root / 'results' / arm / iid / 'trajectory.json'
    if trajectory.exists():
        d = json.loads(trajectory.read_text())
        calls = d.get('native_calls', [])
        report['initial_prompt_tokens'].setdefault(iid, {})[arm] = calls[0]['usage']['prompt_tokens'] if calls else None
        report['pairs'][iid][arm]['output_limit_hits'] = sum(c['finish_reason'] == 'length' for c in d['native_calls'])
        report['pairs'][iid][arm]['format_feedback_count'] = sum(m.get('role') == 'user' and m.get('content', '').startswith('Return exactly one fenced bash command.') for m in d['messages'])
matched = [v for v in report['pairs'].values() if 'control' in v and 'native' in v
           and type(v['control']['resolved']) is bool and type(v['native']['resolved']) is bool]
report['matched_control_native'] = {
    'tasks': len(matched),
    'gains': sum(not v['control']['resolved'] and v['native']['resolved'] for v in matched),
    'regressions': sum(v['control']['resolved'] and not v['native']['resolved'] for v in matched),
    'retained_control_successes': sum(v['control']['resolved'] and v['native']['resolved'] for v in matched),
}
# Grading reports stay outside agent-visible input. Aggregate names into counts.
for path in sorted((a.root / 'logs/run_evaluation').glob('*/*/*/report.json')):
    for iid, result in json.loads(path.read_text()).items():
        arm = path.parts[-4].removeprefix('native-20260926-')
        report['official_test_counts'].setdefault(iid, {})[arm] = {
            group: {outcome: len(cases) for outcome, cases in outcomes.items()}
            for group, outcomes in result.get('tests_status', {}).items()}
a.output.write_text(json.dumps(report, indent=2) + '\n')
