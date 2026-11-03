#!/usr/bin/env python3
"""Check the native client against a fresh, disposable Aimee release stack.

Requires Docker Compose, already pulled release images and an Aimee source
checkout at the release revision (only its test/Compose helpers are consumed).
Never targets an existing service. Credentials live only in a temporary folder.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
import uuid


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aimee-source', type=Path, required=True)
    parser.add_argument('--launcher', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--installed-packages', type=Path,
                        help='optional site-packages with all five dedicated plugins and shared runtime')
    parser.add_argument('--application-image', required=True)
    parser.add_argument('--postgres-image', required=True)
    parser.add_argument('--embedder-image', required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    matrix = load('release_matrix', args.aimee_source / 'tests/e2e/deployment-matrix.py')
    placement = load('release_placement', args.aimee_source / 'tests/e2e/memory-placement-e2e.py')
    pairing = load('release_pairing', args.aimee_source / 'tests/e2e/client-pairing-e2e.py')
    env = dict(os.environ, AIMEE_APPLICATION_IMAGE=args.application_image,
        AIMEE_POSTGRES_IMAGE=args.postgres_image, AIMEE_EMBEDDER_IMAGE=args.embedder_image,
        AIMEE_RUNTIME_WEB_ENABLED='1', COMPOSE_PROFILES='', EMBEDDER_MODEL='bekko-a25m',
        EMBEDDER_URL='https://aimee-embedder:8762', EMBEDDER_DIMS='384')
    stack = matrix.Stack('server', env, args.output)
    stack.project = 'aimee-native-e2e-' + uuid.uuid4().hex[:12]
    stack.application = stack.project + '-aimee-server-1'
    stack.postgres = stack.project + '-aimee-store-db-1'
    stack.embedder = stack.project + '-aimee-embedder-1'
    reservations = []
    for port in (8743, 8443):
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        reservations.append((port, sock))
    stack.network_override.write_text('services:\n  aimee-server:\n    ports: !override\n' +
        ''.join(f'      - "127.0.0.1:{sock.getsockname()[1]}:{port}"\n'
                for port, sock in reservations))
    report = {'checks': [], 'project': stack.project, 'images': {}, 'cleanup': False}
    # Recovery receipt has no credentials and identifies only this owned stack.
    (args.output / 'project.json').write_text(json.dumps({'project': stack.project}) + '\n')

    def check(name, condition):
        report['checks'].append({'name': name, 'passed': bool(condition)})
        print(('PASS ' if condition else 'FAIL ') + name, flush=True)
        if not condition:
            raise RuntimeError(name)

    def wait_ready():
        for _ in range(120):
            state = matrix.command('docker', 'inspect', '--format',
                                   '{{.State.Health.Status}}', stack.application)
            if state == 'healthy':
                return
            time.sleep(2)
        raise RuntimeError('release application readiness timed out')

    try:
        for name in ('application', 'postgres', 'embedder'):
            image = getattr(args, name + '_image')
            report['images'][name] = json.loads(matrix.command('docker', 'image', 'inspect', image))[0]['Id']
        report['phase'] = 'vault_bootstrap'
        matrix.command('python3', str(args.aimee_source / 'scripts/compose-vault-init.py'),
                       *stack.compose_args(), 'up', env=stack.env)
        for _, sock in reservations:
            sock.close()
        report['phase'] = 'application_start'
        stack.compose('up', '-d', '--no-build', '--pull', 'never')
        wait_ready()
        version = matrix.command('docker', 'exec', stack.application, 'aimee', '--version')
        check('application is the expected Aimee v1.0.2 release', '1.0.2' in version)
        report['application_version'] = version
        ports = json.loads(matrix.command('docker', 'inspect', '--format',
                                         '{{json .NetworkSettings.Ports}}', stack.application))
        urls = {}
        for kind, port in (('api', '8743/tcp'), ('web', '8443/tcp')):
            values = ports[port]
            check(kind + ' listener is loopback only', len(values) == 1 and values[0]['HostIp'] == '127.0.0.1')
            urls[kind] = 'https://127.0.0.1:' + values[0]['HostPort']
        gate = placement.Gate(argparse.Namespace(server=stack.application, store_db=stack.postgres))
        with tempfile.TemporaryDirectory(prefix='aimee-native-release-') as private:
            private = Path(private)
            client = private / 'aimee'
            matrix.command('docker', 'cp', stack.application + ':/usr/local/bin/aimee', str(client))
            report['phase'] = 'owner_enrollment'
            browser = pairing.Browser(urls['web'])
            # Bootstrap credentials never enter the evidence or process arguments.
            captured = subprocess.run(['docker', 'logs', stack.application],
                capture_output=True, text=True, check=True, timeout=30)
            logs = captured.stdout + captured.stderr
            creds = {key: re.findall(r'\b' + key + r': ([a-z0-9-]+)', logs)[-1]
                     for key in ('username', 'password')}
            check('bootstrap owner login', browser.request('/api/auth/login', creds)[0] == 200)
            import secrets
            password = secrets.token_hex(24)
            check('permanent disposable owner', browser.request('/api/setup/account', {
                'username': 'nativeowner', 'password': password,
                'password_confirmation': password})[0] == 200)
            check('permanent owner login', browser.request('/api/auth/login', {
                'username': 'nativeowner', 'password': password})[0] == 200)
            status, invitation, _ = browser.request('/api/clients', {'name': 'Native release validation'})
            check('client invitation issued', status == 200 and bool(invitation.get('bearer_token')))
            home = private / 'profile'
            home.mkdir(mode=0o700)
            client_env = dict(os.environ, AIMEE_HOME=str(home), XDG_CONFIG_HOME=str(private / 'xdg'),
                              NO_PROXY='localhost,127.0.0.1', no_proxy='localhost,127.0.0.1')
            # The standard CLI requires its invitation in argv. It is disposable,
            # never printed, and the complete profile is removed by this context.
            paired = subprocess.run([str(client), 'remote', 'set', urls['api'],
                invitation['bearer_token']], env=client_env, capture_output=True, timeout=90)
            check('release thin client enrolls', paired.returncode == 0)
            plugin = private / 'native'
            base = [str(args.launcher.resolve()), '--root', str(plugin)]
            def launch(*command):
                return subprocess.run([*base, *command], env=client_env,
                    capture_output=True, text=True, timeout=90)
            check('native launcher connects to actual enrollment',
                  launch('connect-aimee', '--aimee-home', str(home)).returncode == 0)
            connection = json.loads((plugin / 'config.json').read_text())
            check('plugin stores profile path without copying bearer',
                  connection['thinclient_home'] == str(home) and not Path(connection['token_file']).exists())
            report['phase'] = 'source_lifecycle'
            if args.installed_packages:
                model_client = args.installed_packages / 'aimee_native_runtime/native/aimee-model-client'
                for model in ('gemma4-12b', 'gemma4-26b', 'qwen3-8-27b', 'gemma4-e2b', 'gemma4-e4b'):
                    contract = args.installed_packages / ('aimee_' + model.replace('-', '_')) / 'native/adapter.json'
                    bound_env = dict(client_env, AIMEE_NATIVE_PLUGIN_CONTRACT=str(contract.resolve()))
                    connected = subprocess.run([str(model_client.resolve()), '--root', str(private / model),
                        'connect-aimee', '--aimee-home', str(home)], env=bound_env,
                        capture_output=True, timeout=90)
                    check(model + ' installed shared client enrolls', connected.returncode == 0)
            def current_source():
                result = launch('fetch-primitive', key)
                if result.returncode:
                    return False
                value = json.loads(result.stdout)
                return value.get('schema') == 1 and value.get('records', 0) > 0
            key = 'native-release-' + uuid.uuid4().hex[:10]
            stored = []
            for kind in ('fact', 'preference'):
                status, row = gate.call('store', {'key': 'identity:' + key if kind == 'fact' else key,
                    'kind': kind, 'tier': 'L2', 'content': key + ' ' + kind, 'confidence': 1})
                check('store synthetic ' + kind, status == 200 and row.get('status') == 'ok')
                stored.append(row['id'])
            request = {'task_hint': key, 'session_start': True, 'limit_tokens': 8192, 'store': 'user'}
            status, bank = gate.call('/v1/native/primitive', request)
            check('released source uses schema 1', status == 200 and bank.get('schema') == 1)
            rows = bank['records']
            check('released source is populated and unique', len(rows) >= 2 and
                  len({(r['version']['owner_id'], r['version']['record_id']) for r in rows}) == len(rows))
            check('Rust client accepts populated release primitive', current_source())
            first = stored[0]
            status, before = gate.call('get', {'id': first, 'include_version': True})
            check('current source version available', status == 200 and bool(before.get('memory', {}).get('version')))
            status, changed = gate.call('supersede', {'old_id': first, 'new_content': key + ' corrected',
                                                     'expected_version': before['memory']['version']})
            check('authoritative correction commits', status == 200 and changed.get('status') == 'ok')
            status, updated = gate.call('/v1/native/primitive', request)
            check('release exports corrected source revision', status == 200 and any(
                r['id'] == first and r['content'] == key + ' corrected' and r['version'] == changed['version']
                for r in updated.get('records', [])))
            check('Rust client accepts corrected current source', current_source())
            stack.compose('restart', 'aimee-server')
            wait_ready()
            check('enrollment and source survive application restart', current_source())
            check('revocation accepted by server owner', browser.request('/api/clients/revoke', {'id': invitation['id']})[0] == 200)
            check('Rust native client refuses revoked enrollment', launch('fetch-primitive', key).returncode != 0)
            report['lifecycle_completed'] = True
    except Exception as error:
        # Omit exception messages and command output: either can include credentials.
        report['error_type'] = type(error).__name__
        print('FAIL release validation: ' + type(error).__name__, flush=True)
    finally:
        for _, sock in reservations:
            sock.close()
        try:
            stack.compose('down', '--volumes', '--remove-orphans')
            report['cleanup'] = True
        finally:
            report['passed'] = report['cleanup'] and report.get('lifecycle_completed', False) and 'error_type' not in report
            (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
