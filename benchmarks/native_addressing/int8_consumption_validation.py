"""Frozen INT8 research consumption gate with matched text and prepared controls.

This tests the current instruction contract, not a precision-only comparison with
vLLM. Incorrect answers are retained and never abort the remaining matrix.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import signal
import socketserver
import subprocess
import threading
import time

from campaign import new_json, request
from collect_native_prepare_requests import collect
from hybrid_serving_profile import PROFILE, SYSTEM
from published_campaign import EmptyFallback

REVISION = '1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(rows, tasks):
    wanted = Counter((t['id'], phase, native, turns) for t in tasks
                     for phase, native in [('online', True), ('online', False), ('prepared', True)]
                     for turns in (0, 16, 48))
    observed = Counter((r['task'], r['phase'], r['native'], r['turns']) for r in rows)
    if wanted != observed:
        raise ValueError('incomplete or duplicated matrix')
    by_id = {t['id']: t for t in tasks}
    failures = []
    for row in rows:
        task = by_id[row['task']]
        if row['expected'] != task['answer']:
            raise ValueError('changed frozen answer')
        correct = row['answer'].lower() == task['answer']
        if row['correct'] != correct:
            raise ValueError('inconsistent answer score')
        if row['native']:
            expected = sorted(('public-research-fixture', name, '1') for name in task['expected'])
            actual = sorted(tuple(ref) for ref in row['selected_refs'])
            if actual != expected:
                raise ValueError('canonical selection mismatch: ' + task['id'])
            if row['system_context_sha256'] != hashlib.sha256(SYSTEM.encode()).hexdigest():
                raise ValueError('native instruction binding mismatch')
            if row['phase'] == 'prepared' and row['memory_encoding_passes'] != 0:
                raise ValueError('prepared serving encoded memory')
        if not correct:
            failures.append({k: row[k] for k in ('task', 'phase', 'native', 'turns', 'answer', 'expected')})
    groups = {}
    for phase, native in [('online', True), ('online', False), ('prepared', True)]:
        subset = [r for r in rows if r['phase'] == phase and r['native'] == native]
        groups[phase + ('-native' if native else '-text')] = {'n': len(subset), 'correct': sum(r['correct'] for r in subset)}
    return {'status': 'failed' if failures else 'passed', 'n': len(rows),
            'correct': len(rows) - len(failures), 'groups': groups, 'failures': failures,
            'scope': __doc__}


def main(a):
    gpu = subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.free', '--format=csv,noheader,nounits'], text=True).strip()
    if not gpu.startswith('NVIDIA GeForce RTX 5080,') or int(gpu.rsplit(',', 1)[1]) < 12000:
        raise RuntimeError('requires an idle RTX 5080; no other workload will be stopped')
    cgroup = next(line.split(':', 2)[2].strip() for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0:'))
    if (Path('/sys/fs/cgroup') / cgroup.lstrip('/') / 'memory.max').read_text().strip() == 'max':
        raise RuntimeError('run in a service with finite MemoryMax')
    root = Path(a.output); root.mkdir(mode=0o700)
    tasks = json.loads(Path(a.tasks).read_text())['tasks']
    selection = collect(a.reader, a.archive, tasks)
    new_json(root / 'selection.json', selection)
    new_json(root / 'prepare-requests.json', selection['requests'])
    common = ['--model', a.model, '--placement', a.placement, '--int8',
              '--image-reader', a.reader, '--memory-image', a.archive,
              '--read-gateway', str(root / 'empty.sock'), '--read-authority', 'public-research',
              '--enable-hybrid-native', '--native-candidate-routing', '--memory-limit', '6',
              '--max-active-records', '6']
    protocol = {'tasks': tasks, 'profile': PROFILE, 'system_context': SYSTEM,
             'system_context_sha256': hashlib.sha256(SYSTEM.encode()).hexdigest(),
             'binary_sha256': sha(a.binary), 'reader_sha256': sha(a.reader),
             'suite_sha256': sha(a.tasks), 'placement_sha256': sha(a.placement),
             'model_config_sha256': sha(Path(a.model) / 'config.json'), 'revision': REVISION,
             'turns': [0, 16, 48], 'precision': 'rowwise INT8 research runtime',
             'schedule': 'preload-only', 'frozen_before_run': True}
    server = socketserver.UnixStreamServer(str(root / 'empty.sock'), EmptyFallback)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    rows = []
    previous = {}
    if a.resume:
        prior = Path(a.resume)
        old = json.loads((prior / 'protocol.json').read_text())
        for key in ('tasks', 'profile', 'system_context', 'binary_sha256', 'reader_sha256', 'suite_sha256', 'model_config_sha256', 'revision', 'precision', 'schedule'):
            if old[key] != protocol[key]: raise ValueError('resume identity mismatch: ' + key)
        if json.loads((prior / 'incomplete.json').read_text())['status'] != 'incomplete':
            raise ValueError('resume requires retained incomplete attempt')
        rows = [json.loads(line) for line in (prior / 'rows.jsonl').read_text().splitlines()]
        for row in rows:
            key = (row['task'], row['phase'], row['native'], row['turns'])
            if key in previous: raise ValueError('duplicated retained row')
            previous[key] = row
            data = (prior / row['trace']).read_bytes()
            if hashlib.sha256(data).hexdigest() != row['trace_sha256']: raise ValueError('retained trace changed')
            target = root / row['trace']; target.parent.mkdir(exist_ok=True)
            target.write_bytes(data)
        protocol['retained_stage'] = {'root': str(prior), 'protocol_sha256': sha(prior / 'protocol.json'),
            'placement_sha256': old['placement_sha256'], 'rows': len(rows),
            'reason': 'GPU OOM on first 48-turn text control; all completed answers retained'}
        new_json(root / 'retained-protocol.json', old)
        new_json(root / 'retained-incomplete.json', json.loads((prior / 'incomplete.json').read_text()))
        with (root / 'rows.jsonl').open('x') as stream:
            for row in rows: stream.write(json.dumps(row) + '\n')
    new_json(root / 'protocol.json', protocol)
    try:
        for phase in ('online', 'prepared'):
            if phase == 'prepared':
                cmd = [a.binary, 'prepare-memory', *common, '--requests', str(root / 'prepare-requests.json'),
                       '--prepared-memory', str(root / 'prepared'), '--prepared-model-revision', REVISION,
                       '--memory-encoding', 'system-message', '--trace-dir', str(root / 'prepare-traces')]
                new_json(root / 'prepare-invocation.json', {'argv': cmd})
                with (root / 'prepare.log').open('xb') as log:
                    subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
            traces = root / (phase + '-traces'); traces.mkdir(exist_ok=True)
            cmd = [a.binary, 'serve', *common, '--trace-dir', str(traces), '--port', str(a.port),
                   '--encoding-cache-mib', '256', '--native-schedule', 'preload-only']
            if phase == 'prepared':
                cmd += ['--prepared-memory', str(root / 'prepared'), '--prepared-model-revision', REVISION]
            new_json(root / (phase + '-invocation.json'), {'argv': cmd})
            with (root / (phase + '-server.log')).open('xb') as log:
                proc = subprocess.Popen(cmd, stdout=log, stderr=log, start_new_session=True)
                try:
                    deadline = time.monotonic() + 1800
                    while True:
                        if proc.poll() is not None: raise RuntimeError('model exited during startup')
                        try: request(a.port); break
                        except Exception:
                            if time.monotonic() > deadline: raise RuntimeError('startup timeout')
                            time.sleep(1)
                    for turns in (0, 16, 48):
                        for task in tasks:
                            for native in ([True, False] if phase == 'online' else [True]):
                                key = (task['id'], phase, native, turns)
                                replay = key in previous
                                if replay and not (phase == 'online' and (
                                    (task['id'] == tasks[0]['id'] and turns == 0) or
                                    (task['query'] == 'Which station code is reachable from Osreth outpost?' and turns == 16))):
                                    continue
                                publication = selection['task_bundles'][task['id']]
                                context = SYSTEM
                                if not native:
                                    context += '\n\nAuthoritative memory:\n' + '\n'.join(f['content'] for f in selection['bundle_facts'].get(publication, {'facts': []})['facts'])
                                messages = [{'role': 'system', 'content': context}]
                                for _ in range(turns):
                                    messages += [{'role': 'user', 'content': 'We are planning a meeting.'}, {'role': 'assistant', 'content': 'Understood.'}]
                                messages.append({'role': 'user', 'content': task['query']})
                                result = request(a.port, {'messages': messages, 'max_tokens': 32, 'temperature': 0,
                                         'aimee_memory': native, 'native_recurrent_state': native,
                                         'memory_encoding': 'system-message' if native else 'content', 'memory_encoding_granularity': 'bank'})
                                path = traces / (result['id'] + '.json'); trace = json.loads(path.read_text())
                                refs = {tuple(f['memory_ref'][k] for k in ('namespace', 'id', 'revision'))
                                        for event in trace.get('recall_events') or []
                                        for f in event.get('aimee_response', {}).get('facts', [])}
                                answer = result['choices'][0]['message']['content'].strip().rstrip('.')
                                row = {'task': task['id'], 'phase': phase, 'native': native, 'turns': turns,
                                       'answer': answer, 'expected': task['answer'], 'correct': answer.lower() == task['answer'],
                                       'selected_refs': [list(ref) for ref in sorted(refs)], 'memory_encoding_passes': trace['memory_encoding_passes'],
                                       'system_context_sha256': trace['native_system_context_sha256'],
                                       'elapsed_ms': trace['elapsed_ms'], 'trace': str(path.relative_to(root)), 'trace_sha256': sha(path)}
                                if replay:
                                    if (row['answer'], row['selected_refs']) != (previous[key]['answer'], previous[key]['selected_refs']):
                                        raise ValueError('host-storage placement changed retained answer/selection')
                                    with (root / 'resume-checks.jsonl').open('a') as stream: stream.write(json.dumps(row) + '\n')
                                    print(json.dumps({'replay_check': row}), flush=True)
                                    continue
                                rows.append(row)
                                with (root / 'rows.jsonl').open('a') as stream: stream.write(json.dumps(row) + '\n')
                                print(json.dumps(row), flush=True)
                finally:
                    if proc.poll() is None: os.killpg(proc.pid, signal.SIGTERM)
                    try: proc.wait(timeout=30)
                    except subprocess.TimeoutExpired: os.killpg(proc.pid, signal.SIGKILL); proc.wait()
        report = audit(rows, tasks)
        report.update(rows=rows, protocol_sha256=sha(root / 'protocol.json'))
        new_json(root / 'report.json', report)
        print(json.dumps({k: v for k, v in report.items() if k != 'rows'}), flush=True)
    except BaseException as error:
        new_json(root / 'incomplete.json', {'error': repr(error), 'completed_rows': len(rows), 'status': 'incomplete'})
        raise
    finally:
        server.shutdown(); server.server_close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('output', 'binary', 'model', 'placement', 'reader', 'archive', 'tasks'): p.add_argument('--' + key, required=True)
    p.add_argument('--resume')
    p.add_argument('--port', type=int, default=18946)
    main(p.parse_args())
