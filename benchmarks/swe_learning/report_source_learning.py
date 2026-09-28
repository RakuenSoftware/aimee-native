"""Read-only paired outcome audit for the fixed source-learning campaign."""
import argparse
import json
import pathlib

ARMS = ['source-control', 'source-learn-1', 'source-learn-2', 'source-learn-3']


def audit(root):
    root = pathlib.Path(root)
    tasks = json.loads((root/'tasks.json').read_text())
    if len({task['instance_id'] for task in tasks}) != len(tasks):
        raise ValueError('task list contains duplicate identities')
    rows = []
    partial_files = []
    completed = 0
    arms = {arm:dict(completed=0, passed=0, failed=0, infrastructure_errors=0) for arm in ARMS}
    for task in tasks:
        iid = task['instance_id']
        outcomes = {}
        for arm in ARMS:
            path = root/'results'/arm/iid/'result.json'
            if not path.exists():
                outcomes[arm] = {'status':'pending'}
                continue
            try:
                result = json.loads(path.read_text())
            except json.JSONDecodeError:
                partial_files.append(str(path.relative_to(root)))
                outcomes[arm] = {'status':'pending_write'}
                continue
            if result['instance_id'] != iid or result['arm'] != arm:
                raise ValueError('result identity disagrees with path: '+str(path))
            resolved = result.get('resolved')
            if resolved is not None and type(resolved) is not bool:
                raise ValueError('invalid resolved value')
            status = 'passed' if resolved is True else 'failed' if resolved is False else 'infrastructure_errors'
            outcomes[arm] = {'status':status, 'exit_status':result.get('exit_status'),
                             'grade_status':result.get('grade_status'), 'model_calls':result.get('steps'),
                             'agent_seconds':result.get('agent_seconds')}
            arms[arm]['completed'] += 1
            arms[arm][status] += 1
            completed += 1
        baseline = outcomes[ARMS[0]]['status']
        gained = [arm for arm in ARMS[1:] if baseline=='failed' and outcomes[arm]['status']=='passed']
        lost = [arm for arm in ARMS[1:] if baseline=='passed' and outcomes[arm]['status']=='failed']
        prior_sources = []
        for path in (root/'acquisition').glob('*/'+iid+'/source-experience.json'):
            try:
                experience = json.loads(path.read_text())
            except json.JSONDecodeError:
                partial_files.append(str(path.relative_to(root)))
                continue
            if experience.get('kind')=='accepted_success':prior_sources.append(str(path.relative_to(root)))
        rows.append({'instance_id':iid, 'outcomes':outcomes, 'gained_rounds':gained,
                     'lost_rounds':lost, 'all_native_rounds_passed':all(outcomes[a]['status']=='passed' for a in ARMS[1:]),
                     'prior_accepted_success_sources':prior_sources})
    infrastructure_errors = sum(row['infrastructure_errors'] for row in arms.values())
    status = 'partial'
    if completed == len(tasks)*len(ARMS) and not partial_files:
        status = 'incomplete_grading' if infrastructure_errors else 'complete'
    return {'scope':'Same-task source-experience reuse; repeated rounds are not independent tasks. Partial attempts are not failures.',
            'scheduled_attempts':len(tasks)*len(ARMS), 'completed_attempts':completed,
            'status':status, 'graded_attempts':completed-infrastructure_errors,
            'pending_write_files':partial_files, 'arms':arms,
            'successful_control_tasks':[r['instance_id'] for r in rows if r['outcomes']['source-control']['status']=='passed'],
            'unique_gained_tasks':[r['instance_id'] for r in rows if r['gained_rounds']],
            'unique_lost_tasks':[r['instance_id'] for r in rows if r['lost_rounds']],
            'gains_retained_all_three_rounds':[r['instance_id'] for r in rows if r['gained_rounds'] and r['all_native_rounds_passed']],
            'tasks':rows}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root');parser.add_argument('--output');args=parser.parse_args()
    result=audit(args.root);text=json.dumps(result,indent=2)+'\n'
    if args.output:pathlib.Path(args.output).write_text(text)
    else:print(text,end='')
