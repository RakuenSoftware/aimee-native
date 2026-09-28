"""Regrade an ungraded saved patch without rerunning or changing the agent."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import docker
from swebench.harness.run_evaluation import make_test_spec, run_instance


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--result', type=Path, required=True)
    p.add_argument('--grader-data', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--timeout', type=int, required=True)
    a = p.parse_args()
    original = a.result.resolve().read_bytes()
    row = json.loads(original)
    assert row['resolved'] is None and row['grade_status'] == 'infrastructure_error'
    assert row['model_patch'].strip() and a.timeout > row.get('grade_timeout_seconds', 0)
    definitions = json.loads(a.grader_data.resolve().read_text())
    full = next(r for r in definitions if r['instance_id'] == row['instance_id'])
    output = a.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'running', 'scope': __doc__, 'started': time.time(),
              'original_result_sha256': hashlib.sha256(original).hexdigest(),
              'patch_sha256': hashlib.sha256(row['model_patch'].encode()).hexdigest(),
              'instance_id': row['instance_id'], 'arm': row['arm'], 'timeout': a.timeout,
              'agent_rerun': False, 'resolved': None}
    def save():
        stage = output / 'status.next'
        stage.write_text(json.dumps(report, indent=2) + '\n')
        stage.replace(output / 'status.json')
    save(); os.chdir(output)
    try:
        pred = {'instance_id': row['instance_id'], 'model_name_or_path': 'unchanged-patch-regrade',
                'model_patch': row['model_patch']}
        grade = run_instance(make_test_spec(full, namespace='swebench'), pred, False, False,
                             docker.from_env(), 'saved-patch-regrade', timeout=a.timeout)
        (output / 'grade.json').write_text(json.dumps(grade, indent=2) + '\n')
        if grade is None or not grade['completed']:
            raise RuntimeError('official grader did not complete')
        report.update(status='graded', resolved=bool(grade['resolved']))
    except BaseException as error:
        report.update(status='infrastructure_error', error=repr(error))
        raise
    finally:
        report['finished'] = time.time(); save()


if __name__ == '__main__':
    main()
