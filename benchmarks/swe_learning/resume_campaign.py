"""Resume only after a completely graded prefix; never silently skip attempts."""
import json
import pathlib


def validate_resume(root, tasks, start):
    if start < 0 or start > len(tasks) or start % 2:
        raise ValueError('resume point must be a task-pair boundary')
    root = pathlib.Path(root)
    for task in tasks[:start]:
        for arm in ('source-control','source-learn-1','source-learn-2','source-learn-3'):
            path = root/'results'/arm/task['instance_id']/'result.json'
            if not path.exists():raise ValueError('cannot skip missing attempt: '+str(path))
            row = json.loads(path.read_text())
            if row.get('instance_id') != task['instance_id'] or row.get('arm') != arm:
                raise ValueError('resume result identity mismatch')
            if type(row.get('resolved')) is not bool:
                raise ValueError('cannot skip ungraded attempt: '+str(path))
    return start
