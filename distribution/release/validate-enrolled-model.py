#!/usr/bin/env python3
"""Validate installed model serving against an actual enrolled Aimee profile.

Run only in the owned release-validation environment. Uses synthetic memory,
the normal owner API and enrolled source export; never saves credentials.
"""
import argparse
import hashlib
import http.client
import json
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
import os


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ('config', 'server-home', 'output'):
        parser.add_argument('--' + argument, required=True, type=Path)
    parser.add_argument('--alternate-profile', type=Path,
                        help='Owned enrolled profile for frozen-recipient rejection test')
    args = parser.parse_args()
    args.output.mkdir(mode=0o700)
    config = json.loads(args.config.read_bytes())
    report = {'status': 'running', 'checks': [], 'scope': __doc__}

    def check(name, condition, detail=None):
        report['checks'].append({'name': name, 'passed': bool(condition), 'detail': detail})
        save()
        if not condition:
            raise RuntimeError(name)

    def save():
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    class UnixHTTP(http.client.HTTPConnection):
        def connect(self):
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(120)
            self.sock.connect(str(args.server_home / 'aimee-http.sock'))

    def local(path, body):
        connection = UnixHTTP('localhost', timeout=120)
        connection.request('POST', path, json.dumps(body),
            {'Content-Type': 'application/json', 'X-Aimee-Webuser': 'native-release-owner'})
        response = connection.getresponse()
        status, data = response.status, json.loads(response.read())
        connection.close()
        return status, data

    def store(value):
        status, data = local('/v1/memory/store', {
            'key': 'identity:release-vault',
            'content': 'The workshop vault entry number is ' + value + '.',
            'kind': 'fact', 'tier': 'L2', 'authority': 'user',
            'scope': 'all', 'scope_context': True})
        check('owner-store-' + value, status == 200, {'http_status': status})
        return data['id']

    endpoint = 'http://127.0.0.1:' + str(config['serve']['port'])
    headers = {'Content-Type': 'application/json',
               'Authorization': 'Bearer ' + os.environ['VLLM_API_KEY']}

    def request(authenticated=True):
        body = {'model': config['model'], 'temperature': 0, 'max_tokens': 32,
                'chat_template_kwargs': {'enable_thinking': False},
                'messages': [{'role': 'system', 'content': config['native_system_context']},
                             {'role': 'user', 'content': 'What is the workshop vault entry number?'}]}
        with urllib.request.urlopen(urllib.request.Request(endpoint + '/v1/chat/completions',
                json.dumps(body).encode(), headers=headers if authenticated else {}), timeout=1200) as response:
            return json.load(response)

    catalog = Path(config['catalog'])
    try:
        deadline = time.monotonic() + 900
        while True:
            try:
                with socket.socket(socket.AF_UNIX) as channel:
                    channel.settimeout(3)
                    channel.connect(config['control_socket'])
                    channel.sendall(b'{"op":"status"}\n')
                    status = json.loads(channel.makefile('rb').readline())
                if status.get('state') == 'paused':
                    break
            except (OSError, ValueError):
                pass
            if time.monotonic() > deadline:
                raise RuntimeError('private paused model readiness timeout')
            time.sleep(2)
        check('initially-withdrawn', not json.loads(catalog.read_bytes())['publications'])
        try:
            request(False)
            check('http-auth-required', False)
        except urllib.error.HTTPError as error:
            check('http-auth-required', error.code == 401, {'http_status': error.code})
        check('unauthenticated-request-does-not-select-memory', not json.loads(catalog.read_bytes())['publications'])
        memory_id = store('68731')
        for label, value in [('cold', '68731'), ('warm', '68731'), ('updated', '94562')]:
            if label == 'updated':
                store(value)
            started = time.monotonic()
            result = request()
            answer = result['choices'][0]['message']['content'].strip().rstrip('.')
            check(label + '-recall', answer == value,
                  {'answer': answer, 'seconds': time.monotonic() - started, 'usage': result['usage']})
            raw = catalog.read_bytes()
            current = json.loads(raw)
            check(label + '-bounded-active-bank', len(current['publications']) == 1)
            if label == 'cold':
                first_catalog = hashlib.sha256(raw).hexdigest()
            elif label == 'warm':
                check('warm-bank-reused', hashlib.sha256(raw).hexdigest() == first_catalog)
            else:
                check('changed-source-new-bank', hashlib.sha256(raw).hexdigest() != first_catalog)
        status, data = local('/v1/memory/delete', {'id': memory_id, 'store': 'user'})
        check('ordinary-owner-retirement', status == 200, {'http_status': status})
        result = request()
        answer = result['choices'][0]['message']['content'].strip().rstrip('.')
        check('retired-memory-not-recalled', answer.lower() == 'unknown', {'answer': answer})
        check('empty-source-clears-active-bank', not json.loads(catalog.read_bytes())['publications'])
        store('68731')
        result = request()
        answer = result['choices'][0]['message']['content'].strip().rstrip('.')
        check('restored-source-recalled', answer == '68731', {'answer': answer})
        if args.alternate_profile:
            connection = json.loads((args.config.parent / 'connection.json').read_bytes())
            home = Path(connection['thinclient_home'])
            # Mutate only the disposable profile copied under this test output.
            if not home.resolve().is_relative_to(args.output.resolve().parent):
                raise RuntimeError('recipient-switch test requires an owned disposable profile')
            names = ('tls/client.crt', 'tls/client.key', 'remote.conf')
            originals = {name: (home / name).read_bytes() for name in names}
            try:
                for name in originals:
                    (home / name).write_bytes((args.alternate_profile / name).read_bytes())
                try:
                    request()
                    check('changed-client-identity-denied', False)
                except urllib.error.HTTPError as error:
                    check('changed-client-identity-denied', error.code == 503, {'http_status': error.code})
            finally:
                for name, data in originals.items():
                    (home / name).write_bytes(data)
            result = request()
            answer = result['choices'][0]['message']['content'].strip().rstrip('.')
            check('original-client-identity-recovers', answer == '68731', {'answer': answer})
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        store('68731')
        save()


if __name__ == '__main__':
    main()
