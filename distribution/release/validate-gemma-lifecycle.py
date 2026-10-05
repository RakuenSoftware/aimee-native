#!/usr/bin/env python3
"""Exercise both dedicated Gemma plugins on the owned RTX 5080.

Uses public synthetic prepared banks. Tests serving isolation and lifecycle,
not Aimee account enrollment. Stops only the owned serving service and restores
it even when a release gate fails. All attempt files are retained.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path('/opt/aimee-native-serving')
OUTPUT = ROOT / 'gemma-release-lifecycle-build2'
PROFILES = [('gemma4-12b', 'r6', '12G'), ('gemma4-26b', 'g26-r3', '16G')]


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--clean-environment', type=Path)
    parser.add_argument('--reuse-prepared', type=Path)
    parser.add_argument('--resident-preparation', action='store_true')
    options = parser.parse_args()
    OUTPUT = options.output
    OUTPUT.mkdir(mode=0o700)
    report = {'status': 'running', 'scope': __doc__, 'profiles': []}
    secret = (ROOT / 'credentials.env').read_text().split('=', 1)[1].strip()
    temporary_unit = None
    stopped = False

    def save():
        (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    try:
        subprocess.run(['systemctl', 'stop', 'aimee-native-serving'], check=True)
        stopped = True
        for model, suffix, memory in PROFILES:
            deadline = time.monotonic() + 120
            while subprocess.check_output(['nvidia-smi', '--id=0', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip():
                if time.monotonic() > deadline:
                    raise RuntimeError('5080 occupied; another workload will not be stopped')
                time.sleep(2)
            work = OUTPUT / model
            work.mkdir(mode=0o700)
            config = json.loads((ROOT / ('q4-serving-config-' + suffix + '.json')).read_bytes())
            package = config['python_module']
            python = (options.clean_environment or ROOT / 'env') / 'bin/python'
            original = Path(config['catalog']).read_bytes()
            if options.reuse_prepared:
                original = (options.reuse_prepared / model / 'prepared/catalog.json').read_bytes()
            catalog = work / 'catalog.json'
            catalog.write_bytes(original)
            config.update(catalog=str(catalog), control_socket=str(work / 'control.sock'))
            if options.resident_preparation:
                preparation_root = work / 'resident-prepared'
                preparation_root.mkdir(mode=0o700)
                config.update(native_preparation_enabled=True, preparation_root=str(preparation_root))
            config['serve']['host'] = '127.0.0.1'
            config['serve']['port'] = 18954
            path = work / 'config.json'
            path.write_text(json.dumps(config, indent=2) + '\n')
            profile = {'adapter': model, 'status': 'running', 'checks': [],
                       'original_catalog_sha256': hashlib.sha256(original).hexdigest()}
            report['profiles'].append(profile)
            temporary_unit = 'aimee-native-release-lifecycle-' + model
            env = {'CUDA_VISIBLE_DEVICES': '0', 'PYTHONPATH': str(ROOT / 'installed-model-plugins-final'),
                   'OMP_NUM_THREADS': '8', 'VLLM_NO_USAGE_STATS': '1',
                   'VLLM_CONFIG_ROOT': str(ROOT / 'jit-runtime/config'),
                   'HF_HOME': str(ROOT / 'jit-runtime/huggingface'),
                   'TMPDIR': str(ROOT / 'jit-runtime/tmp'),
                   'XDG_CACHE_HOME': str(ROOT / 'jit-runtime/cache'),
                   'TRITON_CACHE_DIR': str(ROOT / 'jit-runtime/triton')}
            if options.clean_environment:
                env.pop('PYTHONPATH')
                config['library'] = subprocess.check_output([str(python), '-c',
                    'from pathlib import Path; import ' + package + '; print(Path(' + package + '.__file__).parent / "native/libaimee_native.so")'], text=True).strip()
                if not options.reuse_prepared:
                    capture_config = dict(config, offline_prefix_capture=True)
                    capture_config['catalog'] = str(work / 'empty-catalog.json')
                    empty = json.loads(original)
                    empty['publications'] = {}
                    Path(capture_config['catalog']).write_text(json.dumps(empty))
                    capture_path = work / 'capture.json'
                    capture_path.write_text(json.dumps(capture_config))
                    source = ROOT / 'releases/model-plugins-20261004-r1/benchmarks/native_addressing'
                    capture_unit = 'aimee-native-clean-capture-' + model
                    subprocess.run(['systemd-run', '--unit=' + capture_unit, '--wait', '--collect',
                        '--property=MemoryMax=' + memory, '--property=MemorySwapMax=0',
                        '--property=StandardOutput=append:' + str(work / 'capture.log'),
                        '--property=StandardError=append:' + str(work / 'capture.log'),
                        *['--setenv=' + key + '=' + value for key, value in env.items()],
                        str(python), str(source / 'capture_attention_engine.py'), '--config', str(capture_path),
                        '--output', str(work / 'prepared')], check=True, capture_output=True)
                    original = (work / 'prepared/catalog.json').read_bytes()
                    catalog.write_bytes(original)
                    profile['original_catalog_sha256'] = hashlib.sha256(original).hexdigest()
                    profile['preparation'] = json.loads((work / 'prepared/preparation.json').read_bytes())
                    path.write_text(json.dumps(config, indent=2) + '\n')
                else:
                    path.write_text(json.dumps(config, indent=2) + '\n')

            def launch():
                config_socket = Path(config['control_socket'])
                if config_socket.exists():
                    if not config_socket.is_socket():
                        raise RuntimeError('unexpected control socket file')
                    config_socket.unlink()
                subprocess.run(['systemctl', 'reset-failed', temporary_unit], capture_output=True)
                subprocess.run(['systemd-run', '--unit=' + temporary_unit, '--property=MemoryMax=' + memory,
                    '--property=MemorySwapMax=0', '--property=OOMPolicy=stop',
                    '--property=EnvironmentFile=' + str(ROOT / 'credentials.env'),
                    '--property=StandardOutput=append:' + str(work / 'service.log'),
                    '--property=StandardError=append:' + str(work / 'service.log'),
                    *['--setenv=' + key + '=' + value for key, value in env.items()],
                    str(python), '-c', 'from ' + package + '.cli import main; main()',
                    '--config', str(path)], check=True, capture_output=True)
                deadline = time.monotonic() + 900
                while True:
                    try:
                        request = urllib.request.Request('http://127.0.0.1:18954/health', headers={'Authorization': 'Bearer ' + secret})
                        with urllib.request.urlopen(request, timeout=3):
                            break
                    except OSError:
                        if subprocess.run(['systemctl', 'is-active', '--quiet', temporary_unit]).returncode:
                            raise RuntimeError(model + ' exited during startup')
                        if time.monotonic() > deadline:
                            raise RuntimeError(model + ' readiness timeout')
                        time.sleep(2)

            def control(op):
                with socket.socket(socket.AF_UNIX) as sock:
                    sock.settimeout(120)
                    sock.connect(config['control_socket'])
                    sock.sendall(json.dumps(op if isinstance(op, dict) else {'op': op}).encode() + b'\n')
                    return json.loads(sock.makefile('rb').readline())

            def ask(publication='workshop', query='What is the workshop vault entry number?', authenticated=True):
                body = {'model': config['model'], 'messages': [
                    {'role': 'system', 'content': 'Answer the question from authoritative memory. Reply with only the answer. If the answer is absent, reply unknown.'},
                    {'role': 'user', 'content': query}], 'temperature': 0, 'max_tokens': 32,
                    'chat_template_kwargs': {'enable_thinking': False}}
                if publication is not None:
                    body['vllm_xargs'] = {'aimee_publication': publication}
                headers = {'Content-Type': 'application/json'}
                if authenticated:
                    headers['Authorization'] = 'Bearer ' + secret
                request = urllib.request.Request('http://127.0.0.1:18954/v1/chat/completions',
                                                 data=json.dumps(body).encode(), headers=headers)
                try:
                    with urllib.request.urlopen(request, timeout=300) as response:
                        return response.status, json.load(response)
                except urllib.error.HTTPError as error:
                    return error.code, json.load(error)

            def check(name, condition, details):
                profile['checks'].append({'name': name, 'passed': bool(condition), 'details': details})
                save()
                if not condition:
                    raise RuntimeError(model + ': ' + name)

            def canary(name, expected='68731'):
                status, result = ask()
                answer = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip().rstrip('.')
                check(name, status == 200 and answer == expected, {'http_status': status, 'answer': answer})

            launch()
            check('unauthenticated-refused', ask(authenticated=False)[0] == 401, {'expected_status': 401})
            canary('native-canary')
            check('unknown-publication-refused', ask('../another-account')[0] == 400, {'expected_status': 400})
            check('withdrawal', control('withdraw')['state'] == 'withdrawn', {})
            check('withdrawal-blocks-inference', ask()[0] == 503, {'expected_status': 503})
            check('restore', control('refresh')['state'] == 'active', {})
            canary('restored-native-canary')
            empty = json.loads(original)
            empty['publications'] = {}
            control('withdraw')
            catalog.write_text(json.dumps(empty))
            check('empty-catalog-activation', control('refresh')['publications'] == 0, {})
            status, result = ask(None, 'What is 17 plus 24?')
            answer = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip().rstrip('.')
            check('no-memory-control', status == 200 and answer == '41', {'http_status': status, 'answer': answer})
            check('removed-publication-refused', ask()[0] == 400, {'expected_status': 400})
            control('withdraw')
            catalog.write_bytes(original)
            check('republication', control('refresh')['state'] == 'active', {})
            canary('republication-canary')
            if options.resident_preparation:
                withdrawn = control('withdraw')
                prepared = control({'op': 'prepare', 'generation': withdrawn['generation'],
                    'facts': ['The workshop vault entry number is 94562.'], 'context': '',
                    'destination': str(preparation_root / ('a' * 64))})
                check('resident-preparation', prepared.get('state') == 'prepared',
                      {'state': prepared.get('state'), 'error': prepared.get('error')})
                check('preparation-keeps-admission-paused', ask()[0] == 503, {})
                updated = json.loads(original)
                updated['publications'] = {'workshop': prepared['publication']}
                catalog.write_text(json.dumps(updated))
                check('resident-publication-activation', control('refresh')['state'] == 'active', {})
                canary('resident-updated-fact-canary', '94562')
                control('withdraw')
                catalog.write_bytes(original)
                check('resident-original-restore', control('refresh')['state'] == 'active', {})
                canary('resident-original-canary')
            # A complete, structurally valid bank with a different checkpoint
            # identity must be rejected before any worker is mutated.
            tampered = json.loads(original)
            for name, publication in tampered['publications'].items():
                copied = work / ('bad-profile-' + name)
                shutil.copytree(publication['root'], copied)
                provenance_path = copied / 'profile.json'
                provenance = json.loads(provenance_path.read_bytes())
                provenance['weights_sha256'] = '0' * 64
                provenance_path.write_text(json.dumps(provenance))
                publication['root'] = str(copied)
            control('withdraw')
            catalog.write_text(json.dumps(tampered))
            result = control('refresh')
            check('different-checkpoint-rejected', 'error' in result and control('status')['state'] == 'paused', result)
            check('invalid-update-blocks-inference', ask()[0] == 503, {'expected_status': 503})
            catalog.write_bytes(original)
            check('recovery-after-invalid-update', control('refresh')['state'] == 'active', {})
            canary('recovered-native-canary')
            # Wrong recipient never reaches generation. A worker-level rejection
            # requires supervised restart, as documented by the control protocol.
            different = json.loads(original)
            different['recipient'] = 'another-account'
            control('withdraw')
            catalog.write_text(json.dumps(different))
            result = control('refresh')
            check('cross-recipient-refused', 'error' in result and ask()[0] == 503, result)
            check('failed-collective-requires-restart', control('status')['state'] == 'restart_required', {})
            subprocess.run(['systemctl', 'stop', temporary_unit], check=True)
            catalog.write_bytes(original)
            launch()
            canary('supervised-restart-recovery')
            profile.update(status='passed', metrics=control('metrics'))
            save()
            subprocess.run(['systemctl', 'stop', temporary_unit], check=True)
            temporary_unit = None
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        save()
        if temporary_unit:
            subprocess.run(['systemctl', 'stop', temporary_unit], capture_output=True)
        if stopped:
            subprocess.run(['systemctl', 'reset-failed', 'aimee-native-serving'], capture_output=True)
            subprocess.run(['systemctl', 'start', 'aimee-native-serving'], check=True)


if __name__ == '__main__':
    main()
