#!/usr/bin/env python3
"""Installed model GPU gate, invoked inside aimee-release.py's disposable stack.

Profiles are local JSON configurations with real immutable checkpoint hashes.
Only synthetic facts are written. No existing model service is stopped; each
owned process group is terminated, even on failure. Serving logs and enrollment
credentials stay in temporary directories, never in the public report.
"""
import argparse
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def main():
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, lambda *_: signal.default_int_handler(signal.SIGINT, None))
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('profiles', 'aimee-home', 'aimee-source', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--server', required=True)
    p.add_argument('--store-db', required=True)
    a = p.parse_args()
    spec = importlib.util.spec_from_file_location('placement', a.aimee_source / 'tests/e2e/memory-placement-e2e.py')
    placement = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(placement)
    gate = placement.Gate(argparse.Namespace(server=a.server, store_db=a.store_db))
    profiles = json.loads(a.profiles.read_text())
    if not isinstance(profiles, list) or not profiles:
        p.error('--profiles must contain a nonempty JSON array')
    results = [{'model': c['adapter'], 'checks': [], 'passed': False} for c in profiles]
    def save():
        a.output.write_text(json.dumps({'scope': __doc__, 'models': results,
            'passed': all(r['passed'] for r in results)}, indent=2) + '\n')
    save()
    for original, row in zip(profiles, results):
        config = json.loads(json.dumps(original))
        model = config['adapter']
        def check(name, condition):
            row['checks'].append({'name': name, 'passed': bool(condition)})
            save()
            print(('PASS ' if condition else 'FAIL ') + model + ': ' + name, flush=True)
            if not condition:
                raise RuntimeError(name)
        process = None
        mid = None
        # vLLM/ZMQ and the managed control socket require short Unix paths.
        # This directory remains private and is removed by the context manager.
        with tempfile.TemporaryDirectory(prefix='ang-', dir='/tmp') as folder:
            work = Path(folder)
            env = dict(os.environ, PYTHONNOUSERSITE='1', CUDA_VISIBLE_DEVICES='0',
                       OMP_NUM_THREADS='8', VLLM_NO_USAGE_STATS='1', HF_HUB_OFFLINE='1',
                       VLLM_API_KEY=secrets.token_hex(32))
            for key in ('PYTHONPATH', 'PYTHONHOME', 'AIMEE_NATIVE_PLUGIN_CONTRACT', 'VLLM_PLUGINS', 'AIMEE_VLLM_CONFIG'):
                env.pop(key, None)
            for key in ('TMPDIR', 'XDG_CACHE_HOME', 'TRITON_CACHE_DIR', 'VLLM_CONFIG_ROOT', 'HF_HOME'):
                directory = work / key.lower()
                directory.mkdir()
                env[key] = str(directory)
            module = importlib.import_module('aimee_' + model.replace('-', '_'))
            library = Path(module.__file__).parent / 'native/libaimee_native.so'
            config['library'] = str(library)
            row['library_sha256'] = hashlib.sha256(library.read_bytes()).hexdigest()
            row['checkpoint_sha256'] = config.get('gguf_weights_sha256')
            row['checkpoint_profile'] = config.get('gguf_weight_profile', config.get('quantization', 'bf16'))
            row['model_revision'] = config.get('model_revision')
            row['model_config_sha256'] = hashlib.sha256((Path(config['model']) / 'config.json').read_bytes()).hexdigest()
            row['tokenizer_sha256'] = hashlib.sha256((Path(config['model']) / 'tokenizer.json').read_bytes()).hexdigest()
            config['native_system_context'] = 'Use the external memory available to you. Answer with only the requested value. If the external memory lacks the answer, reply unknown. Do not guess.'
            config.setdefault('serve', {})['host'] = '127.0.0.1'
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            config['serve']['port'] = port
            row['serving'] = config['serve']
            path = work / 'model.json'
            path.write_text(json.dumps(config))
            base = [str(Path(sys.executable).parent / ('aimee-' + model)), '--root', str(work / 'managed')]
            def ask(auth=True, changed=False):
                system = config['native_system_context'] + (' changed' if changed else '')
                body = {'model': config['model'], 'temperature': 0, 'max_tokens': 32,
                    'chat_template_kwargs': {'enable_thinking': False}, 'messages': [
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': 'What is the workshop vault entry number?'}]}
                headers = {'Content-Type': 'application/json'}
                if auth:
                    headers['Authorization'] = 'Bearer ' + env['VLLM_API_KEY']
                request = urllib.request.Request('http://127.0.0.1:' + str(port) + '/v1/chat/completions',
                                                 json.dumps(body).encode(), headers)
                try:
                    with urllib.request.urlopen(request, timeout=600) as response:
                        return response.status, json.load(response)
                except urllib.error.HTTPError as error:
                    return error.code, {}
            def recall(label, expected):
                status, body = ask()
                answer = body.get('choices', [{}])[0].get('message', {}).get('content', '').strip().rstrip('.')
                check(label, status == 200 and answer == expected)
            try:
                if config.get('gguf_weights'):
                    row['phase'] = 'checkpoint'
                    digest = hashlib.sha256()
                    with Path(config['gguf_weights']).open('rb') as weights:
                        for block in iter(lambda: weights.read(8 * 1024 * 1024), b''):
                            digest.update(block)
                    check('actual checkpoint matches declared hash',
                          digest.hexdigest() == config.get('gguf_weights_sha256'))
                row['phase'] = 'connect'
                connected = subprocess.run([*base, 'connect-aimee', '--aimee-home', str(a.aimee_home)],
                                           env=env, capture_output=True, timeout=120)
                check('real enrolled profile accepted', connected.returncode == 0)
                row['phase'] = 'startup'
                with (work / 'service.log').open('wb') as log:
                    process = subprocess.Popen([*base, 'serve', '--config', str(path)], env=env,
                                               stdout=log, stderr=log, start_new_session=True)
                deadline = time.monotonic() + 900
                while True:
                    if process.poll() is not None:
                        raise RuntimeError('owned model process exited during startup')
                    try:
                        serving = json.loads((work / 'managed/serving.json').read_text())
                        with socket.socket(socket.AF_UNIX) as control:
                            control.settimeout(2)
                            control.connect(serving['control_socket'])
                            control.sendall(b'{"op":"status"}\n')
                            state = json.loads(control.makefile('rb').readline())
                        # Withdrawn admission deliberately returns HTTP 503,
                        # including /health, until an authorized selection.
                        if state.get('state') == 'paused':
                            break
                    except (OSError, ValueError):
                        pass
                    if time.monotonic() > deadline:
                        raise TimeoutError('model readiness')
                    time.sleep(2)
                check('model ready', True)
                check('missing API key denied', ask(False)[0] == 401)
                value = str(secrets.randbelow(900000) + 100000)
                updated = str(secrets.randbelow(900000) + 100000)
                key = 'identity:native-gpu-' + secrets.token_hex(8)
                row['phase'] = 'source_lifecycle'
                status, stored = gate.call('store', {'key': key, 'content': 'The workshop vault entry number is ' + value + '.',
                    'kind': 'fact', 'tier': 'L2', 'confidence': 1})
                mid = stored.get('id')
                check('synthetic source stored', status == 200 and bool(mid))
                recall('cold native recall', value)
                catalog = Path(json.loads((work / 'managed/serving.json').read_text())['catalog'])
                cold = hashlib.sha256(catalog.read_bytes()).hexdigest()
                recall('warm native recall', value)
                check('warm publication reused', hashlib.sha256(catalog.read_bytes()).hexdigest() == cold)
                if model == 'qwen3-8-27b':
                    # The complete hybrid prefix binds/removes its system turn.
                    # Gemma's attention-only publication has a different contract.
                    check('changed hybrid system context rejected', ask(changed=True)[0] == 400)
                _, before = gate.call('get', {'id': mid, 'include_version': True})
                status, changed = gate.call('supersede', {'old_id': mid,
                    'new_content': 'The workshop vault entry number is ' + updated + '.',
                    'expected_version': before['memory']['version']})
                check('source correction accepted', status == 200 and changed.get('status') == 'ok')
                recall('corrected native recall', updated)
                check('correction produces new publication', hashlib.sha256(catalog.read_bytes()).hexdigest() != cold)
                _, before = gate.call('get', {'id': mid, 'include_version': True})
                status, deleted = gate.call('delete', {'id': mid, 'store': 'user', 'authority': 'user',
                    'expected_version': before['memory']['version']})
                check('source retirement accepted', status == 200 and deleted.get('status') == 'ok')
                mid = None
                recall('retired value no longer recalled', 'unknown')
                row['passed'] = True
            except Exception as error:
                row['error_type'] = type(error).__name__
                # Preserve a private diagnostic outside public evidence until the
                # owning release harness removes its temporary directory.
                if (work / 'service.log').exists():
                    with tempfile.NamedTemporaryFile(prefix='native-gpu-failure-' + model + '-',
                                                     suffix='.log', delete=False) as diagnostic:
                        diagnostic.write((work / 'service.log').read_bytes())
            finally:
                if process is not None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=30)
                if mid:
                    _, before = gate.call('get', {'id': mid, 'include_version': True})
                    gate.call('delete', {'id': mid, 'store': 'user', 'authority': 'user',
                        'expected_version': before['memory']['version']})
                save()
    return 0 if all(r['passed'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
