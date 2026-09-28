"""Release GPUs only after the fixed study has no remaining inference work.

The sole early handoff is the final deferred Requests native attempt after a
normal submission. Its CPU grade remains mandatory before release validation
can be declared complete. No result or benchmark input is changed here.
"""
import argparse
import json
from pathlib import Path


def inspect(root):
    root = Path(root)
    tasks = json.loads((root / 'tasks.json').read_text())
    ids = [t['instance_id'] for t in tasks]
    if len(ids) != 32 or len(set(ids)) != 32:
        raise ValueError('expected the 32 distinct frozen tasks')
    pending = []
    for iid in ids:
        for arm in ('source-control', 'source-learn-1'):
            path = root / 'results' / arm / iid / 'result.json'
            if not path.exists():
                pending.append((iid, arm))
                continue
            row = json.loads(path.read_text())
            if row['instance_id'] != iid or row['arm'] != arm:
                raise ValueError('result identity mismatch')
            if type(row.get('resolved')) is not bool:
                raise ValueError('ungraded infrastructure result: ' + str(path))
    report = dict(gpu_ready=False, grades_complete=not pending, pending=pending)
    if not pending:
        report['gpu_ready'] = True
    elif pending == [('psf__requests-2193', 'source-learn-1')]:
        path = root / 'results/source-learn-1/psf__requests-2193/trajectory.json'
        if path.exists():
            trajectory = json.loads(path.read_text())
            messages = trajectory.get('messages', [])
            report['gpu_ready'] = bool(
                trajectory.get('info', {}).get('exit_status') == 'Submitted'
                and messages and messages[-1].get('role') == 'exit'
                and messages[-1].get('extra', {}).get('exit_status') == 'Submitted')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root')
    args = parser.parse_args()
    print(json.dumps(inspect(args.root)))
