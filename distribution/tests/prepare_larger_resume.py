"""Prepare a separate resume directory; never rewrite original campaign evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def prepare(original, target, regrade):
    state = json.loads((original / 'status.json').read_text())
    if state['status'] != 'failed':
        raise ValueError('original campaign must be terminal failed')
    grade = json.loads((regrade / 'status.json').read_text())
    if grade['status'] != 'graded' or type(grade['resolved']) is not bool or grade['agent_rerun']:
        raise ValueError('completed unchanged-patch regrade required')
    relative = Path('results') / grade['arm'] / grade['instance_id'] / 'result.json'
    raw = (original / relative).read_bytes(); row = json.loads(raw)
    if hashlib.sha256(raw).hexdigest() != grade['original_result_sha256']:
        raise ValueError('original result changed')
    if hashlib.sha256(row['model_patch'].encode()).hexdigest() != grade['patch_sha256']:
        raise ValueError('regrade patch changed')
    if row['resolved'] is not None or row['grade_status'] != 'infrastructure_error':
        raise ValueError('only ungraded infrastructure results may be supplemented')
    files = [p for p in (original / 'results').rglob('*') if p.is_file()]
    source_hashes = {str(p.relative_to(original)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    target.mkdir(parents=True, exist_ok=False)
    for name in ['manifest.json', 'frozen-inputs.json', 'run.py', 'larger_regression.py']:
        shutil.copyfile(original / name, target / name)
    shutil.copytree(original / 'results', target / 'results')
    shutil.copytree(regrade, target / 'saved-patch-regrade')
    result = target / relative
    (result.parent / 'result.original.json').write_bytes(raw)
    row.update(resolved=grade['resolved'], grade_status='graded',
               original_grade_timeout_seconds=row['grade_timeout_seconds'],
               grade_timeout_seconds=grade['timeout'],
               regrade={'path': 'saved-patch-regrade', 'original_result_sha256': grade['original_result_sha256'],
                        'patch_sha256': grade['patch_sha256'], 'agent_rerun': False})
    result.write_text(json.dumps(row, indent=2) + '\n')
    (target / 'resume-provenance.json').write_text(json.dumps({
        'scope': __doc__, 'original_root': str(original), 'original_files_sha256': source_hashes,
        'supplemented_result': str(relative), 'regrade_status_sha256': hashlib.sha256((regrade/'status.json').read_bytes()).hexdigest(),
        'remaining_requests_grade_timeout': 3600}, indent=2) + '\n')
    # Check the untouched original again after preparing the new record.
    for name, digest in source_hashes.items():
        if hashlib.sha256((original / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('original evidence changed while preparing resume')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', type=Path, required=True)
    p.add_argument('--target', type=Path, required=True)
    p.add_argument('--regrade', type=Path, required=True)
    a = p.parse_args(); prepare(a.original, a.target, a.regrade)
