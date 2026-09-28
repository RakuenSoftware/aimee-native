"""Recognize the final CPU-only grade without changing the six-task protocol."""
import hashlib
import json
from pathlib import Path


def inspect(root):
    root = Path(root)
    raw = (root / 'frozen-inputs.json').read_bytes()
    rows = json.loads(raw)
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest['input_sha256'] != hashlib.sha256(raw).hexdigest():
        raise ValueError('input identity mismatch')
    ids = [r['task']['instance_id'] for r in rows]
    if len(ids) != 6 or len(set(ids)) != 6:
        raise ValueError('expected six distinct tasks')
    pending = []
    for iid in ids:
        for arm in ('control', 'text', 'native-1', 'native-2'):
            p = root / 'results' / arm / iid / 'result.json'
            if not p.exists():
                pending.append((iid, arm)); continue
            result = json.loads(p.read_text())
            if result['instance_id'] != iid or result['arm'] != arm:
                raise ValueError('result identity mismatch')
            if type(result.get('resolved')) is not bool:
                raise ValueError('ungraded infrastructure outcome')
    report = dict(gpu_ready=not pending, grades_complete=not pending, pending=pending)
    if pending == [('psf__requests-2193', 'native-2')]:
        p = root / 'results/native-2/psf__requests-2193/trajectory.json'
        if p.exists():
            t = json.loads(p.read_text()); messages = t.get('messages', [])
            report['gpu_ready'] = bool(t.get('info', {}).get('exit_status') == 'Submitted'
                and messages and messages[-1].get('role') == 'exit'
                and messages[-1].get('extra', {}).get('exit_status') == 'Submitted')
    return report
