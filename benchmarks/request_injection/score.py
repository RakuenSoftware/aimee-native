"""Score saved rows only, checking coverage and public-transcript identities."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import statistics


def normalize(answer):
    return answer.strip().lower().rstrip('.').strip()


def main():
    p = argparse.ArgumentParser(); p.add_argument('root', type=Path); args = p.parse_args(); root = args.root
    fixture = json.loads((root/'fixture.json').read_text())
    repetitions = fixture['process_repetitions']
    rows = []
    for rep in range(repetitions):
        completion = json.loads((root/f'completion-{rep}.json').read_text())
        assert completion['passed'] and completion['all_GPU'] and completion['model_files_unchanged']
        rows.extend(json.loads(line) for line in (root/f'rows-{rep}.jsonl').read_text().splitlines())
    expected = {(rep, e['id'], arm, ti) for rep in range(repetitions)
                for e in fixture['episodes'] for arm in fixture['arms'] for ti in range(len(e['turns']))}
    keys = [(r['repeat'], r['episode'], r['arm'], r['turn']) for r in rows]
    assert len(keys) == len(set(keys)) == len(expected) == fixture['requests']
    assert set(keys) == expected
    by_key = {key: row for key, row in zip(keys, rows)}
    for r in rows:
        assert r['physical_devices'] == ['cuda:0'] and r['history_checkpoint_unchanged']
        if r['arm'] != 'native-at-injection': assert r['native_bank_tokens'] == 0
        twin = by_key[(r['repeat'], r['episode'], 'removed-text', r['turn'])]
        assert twin['task_token_ids'] == r['task_token_ids']
        if r['arm'] == 'native-at-injection':
            assert twin['public_transcript_sha256'] == r['public_transcript_sha256']
            assert twin['prior_history_tokens'] == r['prior_history_tokens']
        r['correct'] = normalize(r['answer']) == r['expected']
        r['stale_intrusion'] = r['kind'] == 'withdrawal' and any(
            re.search(r'\b'+re.escape(v)+r'\b', normalize(r['answer'])) for v in r['forbidden'])
    cells = []
    for history in sorted({r['history_target'] for r in rows}):
        for arm in fixture['arms']:
            for kind in ['injection', 'unrelated', 'withdrawal']:
                selected = [r for r in rows if (r['history_target'], r['arm'], r['kind']) == (history, arm, kind)]
                cells.append({'history_target': history, 'arm': arm, 'kind': kind, 'requests': len(selected),
                              'correct': sum(r['correct'] for r in selected),
                              'stale_intrusions': sum(r['stale_intrusion'] for r in selected),
                              'prefill_tokens_mean': statistics.mean(r['prefill_tokens'] for r in selected),
                              'request_first_median_ms': statistics.median(r['request_first_seconds'] for r in selected)*1000,
                              'turn_total_median_ms': statistics.median(r['turn_total_seconds'] for r in selected)*1000,
                              'attachment_median_ms': statistics.median(r['attachment_seconds'] for r in selected)*1000,
                              'cleanup_median_ms': statistics.median(r['cleanup_seconds'] for r in selected)*1000})
    arms = []
    for arm in fixture['arms']:
        selected = [r for r in rows if r['arm'] == arm]
        arms.append({'arm': arm, 'requests': len(selected),
                     'kind_scores': {kind: {'correct': sum(r['correct'] for r in selected if r['kind'] == kind),
                                           'n': sum(r['kind'] == kind for r in selected)} for kind in ['injection', 'unrelated', 'withdrawal']},
                     'stale_intrusions': sum(r['stale_intrusion'] for r in selected),
                     'prefill_tokens': sum(r['prefill_tokens'] for r in selected),
                     'maximum_public_history_tokens': max(r['public_history_tokens'] for r in selected)})
    paired = []
    for history in sorted({r['history_target'] for r in rows}):
        for kind in ['injection', 'unrelated', 'withdrawal']:
            n = [r for r in rows if r['arm'] == 'native-at-injection' and r['history_target'] == history and r['kind'] == kind]
            differences = []
            for r in n:
                t = by_key[(r['repeat'], r['episode'], 'removed-text', r['turn'])]
                differences.append((r['turn_total_seconds']-t['turn_total_seconds'])*1000)
            paired.append({'history_target': history, 'kind': kind, 'n': len(n),
                           'native_minus_removed_total_median_ms': statistics.median(differences)})
    summary = {'passed': True, 'requests': len(rows), 'unique_episodes': len(fixture['episodes']),
               'process_repetitions': repetitions, 'pilot': fixture['pilot'], 'arms': arms, 'cells': cells,
               'paired_turn_cost': paired, 'maximum_cuda_reserved_bytes': max(r['cuda_reserved_bytes'] for r in rows),
               'checks': ['complete paired coverage', 'fixed checkpoint files', 'physical CUDA weights and state',
                          'native and removed task-token identity', 'native and removed public-transcript identity',
                          'history checkpoints unchanged', 'no record text in scoped public history'],
               'raw_sha256': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in root.glob('rows-*.jsonl')},
               'scope': fixture['scope'], 'statistical_unit': 'Episode; turns, shared fixtures and process repeats are dependent.'}
    (root/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({'passed': True, 'requests': len(rows), 'arms': arms, 'paired_turn_cost': paired}, indent=2))


if __name__ == '__main__':
    main()
