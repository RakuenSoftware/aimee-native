"""Verify frozen native-tooling evidence without rewriting or extracting it."""
import hashlib
import json
from pathlib import Path
import tarfile


def verify(repo):
    base = repo / 'benchmarks/serving_validation/native_tooling/evidence'
    roots = [base / '20261014-native-tooling-five-followups',
             base / '20261015-native-plugin-handoff']
    count = 0
    for root in roots:
        for line in (root / 'SHA256SUMS').read_text().splitlines():
            expected, name = line.split('  ', 1)
            path = (root / name).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError('manifest path escapes evidence directory')
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('manifest mismatch: ' + name)
            count += 1

    inventory = json.loads((repo / 'docs/research/native-tooling-data-inventory-20261017.json').read_text())
    actual = {str(f.relative_to(repo)) for root in roots for f in root.rglob('*') if f.is_file()}
    expected = {item['path'] for item in inventory['files']}
    if actual != expected or len(expected) != inventory['file_count']:
        raise ValueError('evidence inventory is incomplete or contains duplicate paths')
    for item in inventory['files']:
        path = (repo / item['path']).resolve()
        if not any(path.is_relative_to(root.resolve()) for root in roots):
            raise ValueError('inventory path escapes evidence directories')
        raw = path.read_bytes()
        if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('inventory mismatch: ' + item['path'])

    rows = [json.loads(line) for line in (roots[1] / 'results.jsonl').read_text().splitlines()]
    if rows[-1]['kind'] != 'terminal' or not all(s['closed'] for s in rows[-1]['states'].values()):
        raise ValueError('handoff run is not terminal with closed owner sessions')
    models = [row for row in rows if row['kind'] == 'model']
    summary = json.loads((roots[1] / 'summary.json').read_text())
    if len(models) != summary['task_model_calls']:
        raise ValueError('model call count mismatch')
    if sum(row['response']['usage']['prompt_tokens'] for row in models) != summary['ordinary_prompt_tokens']:
        raise ValueError('ordinary task input accounting mismatch')
    states = {row['task']: row['reply']['state'] for row in rows if row['kind'] == 'episode'}
    if states != summary['episode_states']:
        raise ValueError('episode outcome mismatch')
    for row in (row for row in rows if row['kind'] == 'withdraw'):
        if row['metrics']['active_requests'] != 0 or any(w.get('pinned_requests', 0) != 0 for w in row['metrics']['workers']):
            raise ValueError('worker cleanup was not confirmed')

    with tarfile.open(roots[1] / 'remote-run.tar.gz') as archive:
        members = {m.name.removeprefix('./'): m for m in archive.getmembers() if m.isfile()}
        for effect in (row for row in rows if row['kind'] == 'fixture_effect' and row['tool'] == 'write_file'):
            raw = archive.extractfile(members[Path(effect['path']).name]).read()
            if hashlib.sha256(raw).hexdigest() != effect['sha256'] or raw.decode() != effect['content']:
                raise ValueError('observed fixture effect mismatch')
        source = archive.extractfile(members['native_handoff.py']).read()
        if source != (repo / 'distribution/vllm/aimee_vllm/native_handoff.py').read_bytes():
            raise ValueError('plugin source differs from frozen model experiment')
    return dict(original_manifest_entries=count, inventory_files=len(actual),
                model_calls=len(models), episode_states=states, verified=True)


if __name__ == '__main__':
    print(json.dumps(verify(Path(__file__).resolve().parents[3]), indent=2))
