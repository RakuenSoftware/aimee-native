"""Matched installed-wheel coding validation using frozen, complete source memories.

Six previously selected SWE-bench issues, not an unseen benchmark sample. Uses
explicit research publication selection to isolate consumer task quality; this
is not a new test of live Aimee retrieval. Official grading remains outside agent
containers. Native repeat reuses frozen memory and is not a learning round.
"""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.request
import run

ARMS = ('control', 'text', 'native', 'native-repeat')


def main():
    root = run.ROOT
    os.chdir(root)
    rows = json.loads((root / 'frozen-inputs.json').read_text())
    manifest = json.loads((root / 'manifest.json').read_text())
    assert len(rows) == len({r['task']['instance_id'] for r in rows}) == 6
    assert hashlib.sha256((root / 'frozen-inputs.json').read_bytes()).hexdigest() == manifest['input_sha256']
    assert hashlib.sha256((root / 'run.py').read_bytes()).hexdigest() == manifest['runner_sha256']
    assert (run.CONTEXT_TOKENS, run.OUTPUT_TOKENS, run.STEPS, run.SECONDS) == (8192, 1536, 60, 900)
    run.GRADER = {t['instance_id']: t for t in json.loads(Path('/opt/swe-native/selected-grader-only.json').read_text())}
    with urllib.request.urlopen(run.BASE + '/v1/models', timeout=30) as response:
        run.MODEL = json.load(response)['data'][0]['id']
    state = {'status': 'running', 'scope': __doc__, 'started': time.time(), 'model': run.MODEL,
             'manifest': manifest, 'target_attempts': 24,
             'budgets': {'context_tokens': run.CONTEXT_TOKENS, 'input_tokens': run.INPUT_TOKENS,
                         'output_tokens': run.OUTPUT_TOKENS, 'steps': run.STEPS,
                         'agent_seconds': run.SECONDS, 'concurrency': 2}, 'results': [], 'active': {}}
    lock = threading.Lock()
    stopped = threading.Event()

    def save():
        state['updated'] = time.time()
        state['arms'] = {arm: {'completed': len(rs := [r for r in state['results'] if r['arm'] == arm]),
                              'resolved': sum(r['resolved'] is True for r in rs),
                              'infrastructure_errors': sum(r['resolved'] is None for r in rs)} for arm in ARMS}
        tmp = root / 'status.next'
        tmp.write_text(json.dumps(state, indent=2) + '\n')
        tmp.replace(root / 'status.json')

    def task_entry(number, row):
        task = row['task']; iid = task['instance_id']
        assert not {'patch', 'test_patch', 'FAIL_TO_PASS', 'PASS_TO_PASS'} & task.keys()
        assert hashlib.sha256(row['fact'].encode()).hexdigest() == row['fact_sha256']
        pub = manifest['publications'][iid]
        assert pub['fact_sha256'] == row['fact_sha256'] and pub['complete_memory_token_count_verified']
        # Rotate order of all three delivery conditions, then repeat native.
        orders = [('control', 'text', 'native'), ('text', 'native', 'control'), ('native', 'control', 'text')]
        for arm in (*orders[number % 3], 'native-repeat'):
            if stopped.is_set():
                return
            with lock:
                state['active'][iid] = arm; save()
            result = run.attempt(task, arm, pub['publication'] if arm.startswith('native') else None,
                                 row['fact'] if arm == 'text' else None)
            trajectory = root / 'results' / arm / iid / 'trajectory.json'
            if trajectory.exists():
                data = json.loads(trajectory.read_text())
                calls = data['native_calls']
                expected = pub['publication'] if arm.startswith('native') else None
                assert calls and all(c['publication'] == expected for c in calls)
                assert data['text_memory'] == (row['fact'] if arm == 'text' else None)
                # Preserve raw trajectory even if the installed harness schema differs.
                result['trajectory_sha256'] = hashlib.sha256(trajectory.read_bytes()).hexdigest()
                result['metered_calls'] = len(calls)
                result['tokens'] = {k: sum(c.get('usage', {}).get(k, 0) for c in calls)
                                   for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
                result['model_seconds'] = sum(c['seconds'] for c in calls)
            with lock:
                state['results'].append(result); state['active'].pop(iid, None); save()
            if type(result.get('resolved')) is not bool:
                stopped.set()
                raise RuntimeError(f'{iid}/{arm}: infrastructure error, not a scored task failure')
    save()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(task_entry, i, row) for i, row in enumerate(rows)]
            for future in concurrent.futures.as_completed(futures):
                future.result()
        assert len(state['results']) == 24
        state['pairs'] = {r['task']['instance_id']: {x['arm']: x['resolved'] for x in state['results']
                          if x['instance_id'] == r['task']['instance_id']} for r in rows}
        state['status'] = 'complete'
    except BaseException as error:
        state.update(status='failed', error=repr(error)); raise
    finally:
        save()


if __name__ == '__main__':
    main()
