"""Fresh matched controls and repeated native reuse of frozen accepted procedures.

Selected regression/transfer cases, not held-out population learning effects.
Official grader data stays outside agent containers and memory preparation.
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


def main():
    root = run.ROOT; os.chdir(root)
    inputs = root / 'frozen-inputs.json'; rows = json.loads(inputs.read_text())
    manifest = json.loads((root / 'manifest.json').read_text())
    assert len(rows) == 6 and len({r['task']['instance_id'] for r in rows}) == 6
    assert manifest['input_sha256'] == hashlib.sha256(inputs.read_bytes()).hexdigest()
    assert (run.CONTEXT_TOKENS, run.OUTPUT_TOKENS, run.STEPS, run.SECONDS) == (4096, 1536, 40, 600)
    run.GRADER = {t['instance_id']: t for t in json.loads(Path('/opt/swe-native/selected-grader-only.json').read_text())}
    with urllib.request.urlopen(run.BASE + '/v1/models', timeout=30) as response:
        run.MODEL = json.load(response)['data'][0]['id']
    state = {'status': 'running', 'scope': __doc__, 'started': time.time(), 'model': run.MODEL,
             'profile': manifest['profile'], 'input_sha256': manifest['input_sha256'],
             'budgets': {'steps': run.STEPS, 'agent_seconds': run.SECONDS, 'context_tokens': run.CONTEXT_TOKENS,
                         'input_tokens': run.INPUT_TOKENS, 'output_tokens': run.OUTPUT_TOKENS, 'concurrency': 2},
             'results': []}
    lock = threading.Lock()
    stopped = threading.Event()
    def save():
        state['updated'] = time.time()
        tmp = root / 'status.next'; tmp.write_text(json.dumps(state, indent=2) + '\n'); tmp.replace(root / 'status.json')
    def attempt_entry(number, row):
        task = row['task']; iid = task['instance_id']
        assert not {'patch', 'test_patch', 'FAIL_TO_PASS', 'PASS_TO_PASS'} & task.keys()
        assert hashlib.sha256(row['fact'].encode()).hexdigest() == row['fact_sha256']
        pub = manifest['publications'][iid]
        assert pub['fact_sha256'] == row['fact_sha256'] and pub['complete_memory_token_count_verified']
        # Counterbalance control/text order across the six fixed tasks.
        arms = (['control', 'text'] if number % 2 == 0 else ['text', 'control']) + ['native-1', 'native-2']
        for arm in arms:
            if stopped.is_set():
                return
            result = run.attempt(task, arm,
                pub['publication'] if arm.startswith('native') else None,
                row['fact'] if arm == 'text' else None)
            with lock:
                state['results'].append(result); save()
            if type(result.get('resolved')) is not bool:
                stopped.set()
                raise RuntimeError(f'{iid}/{arm} has no official outcome; stop rather than count infrastructure as failure')
    save()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt_entry, i, row) for i, row in enumerate(rows)]
            for future in concurrent.futures.as_completed(futures):
                future.result()
        state['status'] = 'complete'
        state['arms'] = {arm: {'attempts': len(rs := [r for r in state['results'] if r['arm'] == arm]),
                               'resolved': sum(r['resolved'] is True for r in rs)}
                         for arm in ('control', 'text', 'native-1', 'native-2')}
        state['pairs'] = {}
        for row in rows:
            iid = row['task']['instance_id']
            outcomes = {r['arm']: r['resolved'] for r in state['results'] if r['instance_id'] == iid}
            state['pairs'][iid] = outcomes
        assert len(state['results']) == 24
    except BaseException as error:
        state.update(status='failed', error=repr(error)); raise
    finally:
        save()


if __name__ == '__main__':
    main()
