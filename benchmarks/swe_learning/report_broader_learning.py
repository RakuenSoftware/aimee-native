"""Read-only paired report for the 32-task follow-up; never pools primary rounds."""
import argparse
import json
import pathlib

ARMS = ('source-control', 'source-learn-1')


def audit(root):
    root = pathlib.Path(root)
    tasks = json.loads((root / 'tasks.json').read_text())
    ids = [task['instance_id'] for task in tasks]
    if len(ids) != 32 or len(set(ids)) != len(ids):
        raise ValueError('expected 32 distinct frozen follow-up tasks')
    rows = []
    totals = {arm: dict(passed=0, failed=0, ungraded=0, pending=0) for arm in ARMS}
    paired = dict(both_pass=0, control_only=0, native_only=0, both_fail=0, incomplete=0)
    for iid in ids:
        outcomes = {}
        for arm in ARMS:
            path = root / 'results' / arm / iid / 'result.json'
            try:
                result = json.loads(path.read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                outcomes[arm] = dict(status='pending')
                totals[arm]['pending'] += 1
                continue
            if result['instance_id'] != iid or result['arm'] != arm:
                raise ValueError('result identity disagrees with path: ' + str(path))
            resolved = result.get('resolved')
            if resolved is not None and type(resolved) is not bool:
                raise ValueError('resolved must be a boolean or null')
            status = 'passed' if resolved is True else 'failed' if resolved is False else 'ungraded'
            totals[arm][status] += 1
            outcomes[arm] = dict(status=status, grade_status=result.get('grade_status'),
                                 exit_status=result.get('exit_status'),
                                 model_calls=result.get('steps'), agent_seconds=result.get('agent_seconds'))
        statuses = tuple(outcomes[a]['status'] for a in ARMS)
        category = {('passed', 'passed'): 'both_pass', ('passed', 'failed'): 'control_only',
                    ('failed', 'passed'): 'native_only', ('failed', 'failed'): 'both_fail'}.get(statuses, 'incomplete')
        paired[category] += 1
        rows.append(dict(instance_id=iid, pair=category, outcomes=outcomes))
    ungraded = sum(t['ungraded'] for t in totals.values())
    pending = sum(t['pending'] for t in totals.values())
    return dict(status='partial' if pending else 'incomplete_grading' if ungraded else 'complete',
                scope='Additional frozen tasks; one control followed by one native reuse attempt. No prior calibration memory supplied. A second attempt alone is not isolated from a memory effect; no three-round retention or held-out generalization claim.',
                scheduled_attempts=64, graded_attempts=64-pending-ungraded,
                arms=totals, paired_tasks=paired,
                unique_gained_tasks=[r['instance_id'] for r in rows if r['pair']=='native_only'],
                unique_lost_tasks=[r['instance_id'] for r in rows if r['pair']=='control_only'], tasks=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root')
    parser.add_argument('--output')
    args = parser.parse_args()
    text = json.dumps(audit(args.root), indent=2) + '\n'
    if args.output:
        pathlib.Path(args.output).write_text(text)
    else:
        print(text, end='')
