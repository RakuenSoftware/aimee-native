"""Operator-only validation of a dedicated, real Aimee canary publication.

Runs on the publisher host. Never point this at an ordinary recipient: expiry,
withdrawal and authority disconnect are intentional. No credentials are read.
"""
import argparse
import datetime
import json
import os
import pathlib
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument('--config', required=True)
p.add_argument('--policy', required=True)
p.add_argument('--preparer', required=True)
p.add_argument('--user', required=True)
p.add_argument('--publisher-unit', required=True)
p.add_argument('--expected-records', type=int, required=True)
p.add_argument('--output', required=True)
a = p.parse_args()
policy = pathlib.Path(a.policy)
original = policy.read_bytes()
metadata = policy.stat()
results = {}


def write(raw):
    temporary = policy.with_suffix('.lifecycle.tmp')
    with temporary.open('wb') as f:
        os.fchmod(f.fileno(), metadata.st_mode & 0o777)
        os.fchown(f.fileno(), metadata.st_uid, metadata.st_gid)
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    temporary.replace(policy)


def prepare(check=False):
    command = ['runuser', '-u', a.user, '--', a.preparer, a.config]
    if check:
        command += ['--check']
    return subprocess.run(command, capture_output=True, timeout=600)


def await_state(available):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = prepare(True)
        if (result.returncode == 0) == available:
            return
        time.sleep(0.2)
    raise RuntimeError('publication state did not converge')


def service(action):
    subprocess.run(['systemctl', action, a.publisher_unit], check=True, capture_output=True)


try:
    await_state(True)
    # Availability means current authorization, not an already populated cache.
    # A new encoding revision legitimately requires one fresh preparation.
    first = prepare()
    if first.returncode:
        raise RuntimeError('initial approved preparation failed')
    initial = json.loads(first.stdout)
    assert len(initial['records']) == a.expected_records, 'partial initial working set'
    results['initial_preparation'] = {'passed': True, 'reused': initial['reused'],
                                      'records': len(initial['records']), 'key': initial['key']}
    started = time.perf_counter()
    result = prepare()
    if result.returncode:
        raise RuntimeError('approved preparation failed')
    prepared = json.loads(result.stdout)
    assert len(prepared['records']) == a.expected_records, 'partial working set'
    assert prepared['key'] == initial['key'], 'unchanged preparation identity drifted'
    assert prepared['records'] == initial['records'], 'unchanged selected records drifted'
    assert prepared['reused'] is True, 'previous real preparation was not reused'
    results['reuse'] = {'passed': True, 'records': len(prepared['records']),
                        'elapsed_ms': round((time.perf_counter() - started) * 1000, 3),
                        'view': prepared['authorized_view'], 'key': prepared['key']}
    for name in ['expired', 'withdrawn']:
        release = json.loads(original)
        if name == 'expired':
            release['valid_until'] = '2000-01-01T00:00:00Z'
        else:
            release['active'] = False
        write(json.dumps(release).encode())
        await_state(False)
        denied = prepare()
        assert denied.returncode != 0, 'revoked cached preparation admitted'
        results[name] = {'passed': True, 'cached_preparation_denied': True}
        write(original)
        await_state(True)
    service('stop')
    await_state(False)
    assert prepare().returncode != 0, 'disconnected cached preparation admitted'
    results['disconnected'] = {'passed': True, 'cached_preparation_denied': True}
    service('start')
    await_state(True)
    restored = prepare()
    assert restored.returncode == 0 and json.loads(restored.stdout)['reused'] is True
    results['recovered'] = {'passed': True, 'prepared_cache_reused': True}
finally:
    write(original)
    service('start')
    pathlib.Path(a.output).write_text(json.dumps({'scope': 'live Aimee canary source and operator-scoped publication; frontend/GPU tested separately', 'results': results}, indent=2) + '\n')
print(json.dumps(results))
