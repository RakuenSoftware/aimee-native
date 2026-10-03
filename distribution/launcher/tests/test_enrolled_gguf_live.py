"""Physical release smoke: enrolled thin client -> local GGUF -> live vLLM.

Run on a supported GPU host with the candidate wheel installed:
  python test_enrolled_gguf_live.py MODEL_DIRECTORY [PORT]
The model directory must contain one GGUF and its configuration/tokenizer.
"""
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def cert(base, name, extra, authority=None):
    key, crt = base / f'{name}.key', base / f'{name}.crt'
    command = ['openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-subj', f'/CN={name}',
               '-keyout', str(key)]
    if authority is None:
        subprocess.run(command + ['-x509', '-days', '1', '-addext',
            'basicConstraints=critical,CA:TRUE', '-out', str(crt)],
            check=True, capture_output=True)
    else:
        csr, extension = base / f'{name}.csr', base / f'{name}.ext'
        subprocess.run(command + ['-out', str(csr)], check=True, capture_output=True)
        extension.write_text(extra + '\n')
        subprocess.run(['openssl', 'x509', '-req', '-in', str(csr), '-CA', str(authority[1]),
            '-CAkey', str(authority[0]), '-CAcreateserial', '-days', '1', '-out', str(crt),
            '-extfile', str(extension)], check=True, capture_output=True)
    return key, crt


class Primitive(BaseHTTPRequestHandler):
    revoked = False

    def do_POST(self):
        peer = self.connection.getpeercert()
        cn = dict(item[0] for item in peer.get('subject', ())).get('commonName') if peer else None
        if (self.revoked or self.path != '/v1/native/primitive' or cn != 'thin-client'
                or self.headers.get('Authorization') != 'Bearer enrolled-token'):
            self.send_error(403)
            return
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert request['store'] == 'user'
        if (request['task_hint'] == 'native memory connection'
                or os.environ.get('AIMEE_LIVE_EMPTY_CONTROL') == '1'):
            facts = []
        elif os.environ.get('AIMEE_LIVE_REFERENCE') == '1':
            facts = [
                (7, 'The release verification vault code is 28461.'),
                (8, 'The release verification project is Juniper.'),
                (9, 'The release verification drink is hibiscus tea.'),
            ]
        elif os.environ.get('AIMEE_LIVE_NEUTRAL') == '1':
            facts = [
                (7, 'The release verification project codename is Halcyon.'),
                (8, 'The release verification notebook color is blue.'),
            ]
        else:
            facts = [
                (7, 'The project codename is Halcyon.'),
                (8, 'The owner prefers blue notebooks.'),
            ]
        records = [{'id': identifier, 'content': content, 'version': {
            'schema_version': 1, 'owner_id': '00000000-0000-0000-0000-000000000001',
            'record_id': str(identifier), 'record_revision': '1'}}
            for identifier, content in facts]
        body = json.dumps({'schema': 1, 'records': records}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def request(port, prompt=None, messages=None):
    default_prompt = (
        'Give the release verification vault code, project, and drink. Be concise.'
        if os.environ.get('AIMEE_LIVE_REFERENCE') == '1' else
        'What are the release verification project codename and notebook color? Reply in one sentence.'
        if os.environ.get('AIMEE_LIVE_NEUTRAL') == '1' else
        'What is the project codename, and what color notebooks does the owner prefer? Reply in one sentence.')
    body = {'model': str(model), 'messages': messages or [{'role': 'user', 'content':
        prompt or default_prompt}],
        'temperature': 0, 'max_tokens': 80,
        'chat_template_kwargs': {'enable_thinking': False}}
    return urlopen(Request(f'http://127.0.0.1:{port}/v1/chat/completions',
        data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'}),
        timeout=float(os.environ.get('AIMEE_LIVE_REQUEST_TIMEOUT', '1200')))


model = Path(sys.argv[1]).resolve()
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8189
with tempfile.TemporaryDirectory(prefix='aimee-enrolled-live-') as temporary:
    base = Path(temporary)
    ca = cert(base, 'test-ca', '')
    server_key, server_crt = cert(base, 'localhost',
        'subjectAltName=DNS:localhost\nextendedKeyUsage=serverAuth', ca)
    client_key, client_crt = cert(base, 'thin-client', 'extendedKeyUsage=clientAuth', ca)
    server = HTTPServer(('127.0.0.1', 0), Primitive)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(str(server_crt), str(server_key))
    tls.verify_mode = ssl.CERT_REQUIRED
    tls.load_verify_locations(str(ca[1]))
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    home = base / 'thinclient'
    (home / 'tls').mkdir(parents=True)
    endpoint = f'https://localhost:{server.server_port}'
    for name, contents in {'remote.conf': endpoint + '\nenrolled-token\n',
            'remote-ca.pem': ca[1].read_text(), 'tls/client.crt': client_crt.read_text(),
            'tls/client.key': client_key.read_text()}.items():
        target = home / name
        target.write_text(contents)
        os.chmod(target, 0o600)
    root = base / 'plugin'
    env = dict(os.environ, NO_PROXY='localhost,127.0.0.1', no_proxy='localhost,127.0.0.1',
               VLLM_USE_FLASHINFER_SAMPLER='0', HF_HUB_OFFLINE='1')
    launcher = [str(Path(sys.executable).parent / 'aimee-native'), '--root', str(root)]
    connected = subprocess.run(launcher + ['connect-aimee', '--aimee-home', str(home)],
        text=True, capture_output=True, env=env)
    assert connected.returncode == 0, (connected.stdout, connected.stderr)
    assert not (root / 'credentials').exists()
    config = base / 'serve.json'
    settings = {'model': str(model),
        'gguf_matrix_backend': os.environ.get('AIMEE_LIVE_MATRIX_BACKEND', 'triton'),
        'max_memory_tokens': 1024, 'serve': {'port': port,
        'tensor_parallel_size': int(os.environ.get('AIMEE_LIVE_TP', '1')),
        'max_model_len': 2048, 'max_num_seqs': 1, 'max_num_batched_tokens': 128,
        'gpu_memory_utilization': float(os.environ.get('AIMEE_LIVE_GPU_MEMORY_UTILIZATION', '0.92'))}}
    if (model / 'mmproj.gguf').is_file():
        settings['gguf_weights'] = str(model / 'model.gguf')
        settings['mm_proj'] = str(model / 'mmproj.gguf')
    config.write_text(json.dumps(settings))
    log = (base / 'serve.log').open('w+')
    process = subprocess.Popen(launcher + ['serve', '--config', str(config)],
        stdout=log, stderr=subprocess.STDOUT, env=env)
    try:
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(f'serve exited {process.returncode}; log: {base / "serve.log"}')
            try:
                # Native admission starts paused until its first approved
                # selection. /health is deliberately 503 in that state.
                with urlopen(f'http://127.0.0.1:{port}/v1/models', timeout=2):
                    break
            except (HTTPError, URLError, TimeoutError):
                time.sleep(2)
        else:
            raise AssertionError(f'serve did not become healthy; log: {base / "serve.log"}')
        if os.environ.get('AIMEE_LIVE_EMPTY_CONTROL') == '1':
            with request(port, messages=[
                    {'role': 'system', 'content':
                     'The release verification project codename is Halcyon. '
                     'The release verification notebook color is blue.'},
                    {'role': 'user', 'content':
                     'What are the release verification project codename and notebook color?'}]) as response:
                result = json.load(response)
            answer = result['choices'][0]['message']['content']
            count = len(list(root.rglob('compact.pack')))
            print(json.dumps({'answer': answer, 'usage': result['usage'],
                              'bank_count': count, 'condition': 'text-no-native'}), flush=True)
            assert count == 0 and 'Halcyon' in answer and 'blue' in answer.lower(), answer
            sys.exit(0)
        if os.environ.get('AIMEE_LIVE_REFERENCE') == '1':
            reference_cases = [
                (None, ('28461', 'Juniper', 'hibiscus')),
                ('What is the release verification vault code? Return only the code.', ('28461',)),
                ('What is the release verification project? Return only the name.', ('Juniper',)),
                ('What is the release verification drink? Return only the drink.', ('hibiscus',)),
            ]
            for prompt, expected in reference_cases:
                with request(port, prompt) as response:
                    result = json.load(response)
                answer = result['choices'][0]['message']['content']
                count = len(list(root.rglob('compact.pack')))
                print(json.dumps({'answer': answer, 'usage': result['usage'],
                    'bank_count': count, 'prompt': prompt,
                    'condition': 'native-three-record'}), flush=True)
                assert result['usage']['prompt_tokens'] < 80, result['usage']
                assert count == 1 and all(value.lower() in answer.lower()
                                          for value in expected), answer
            Primitive.revoked = True
            try:
                with request(port):
                    raise AssertionError('revoked memory request was served')
            except HTTPError as error:
                assert error.code == 503, (error.code, error.read())
            print('revoked thin-client authorization withdrew native serving')
            sys.exit(0)
        prompts = [None]
        if os.environ.get('AIMEE_LIVE_PROBE') == '1':
            if os.environ.get('AIMEE_LIVE_NEUTRAL') == '1':
                prompts += [
                    'Use the available release verification facts. What are the project codename and notebook color?',
                    'State the release verification project codename and notebook color in one sentence.',
                ]
            else:
                prompts += [
                    'Use the authoritative memory available to you. What is the project codename and the notebook color? Answer with both facts.',
                    'From your available memory, state the project codename and notebook color in one sentence.',
                ]
        answered = False
        for prompt in prompts:
            with request(port, prompt) as response:
                result = json.load(response)
            answer = result['choices'][0]['message']['content']
            print(json.dumps({'answer': answer, 'usage': result['usage'],
                'bank_count': len(list(root.rglob('compact.pack'))), 'prompt': prompt}), flush=True)
            assert result['usage']['prompt_tokens'] < 80, result['usage']
            if 'Halcyon' in answer and 'blue' in answer.lower():
                answered = True
                break
        assert answered, 'native memory did not answer both selected facts'
        Primitive.revoked = True
        try:
            with request(port):
                raise AssertionError('revoked memory request was served')
        except HTTPError as error:
            assert error.code == 503, (error.code, error.read())
        print('revoked thin-client authorization withdrew native serving')
    except Exception:
        log.flush()
        log.seek(0)
        print(log.read()[-60000:], file=sys.stderr)
        raise
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        server.shutdown()
        server_thread.join(timeout=5)
        server.server_close()
        log.flush()
        if process.returncode not in (0, -15):
            log.seek(0)
            print(log.read()[-60000:], file=sys.stderr)
        log.close()
