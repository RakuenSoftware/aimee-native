"""Exercise the production launcher's private-address TLS connection, without GPU."""
import argparse
import hashlib
import http.server
import json
import pathlib
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.parse
import unittest

parser = argparse.ArgumentParser()
parser.add_argument('--launcher', required=True)
args, remaining = parser.parse_known_args()


class NamedTLS(unittest.TestCase):
    def test_address_override_still_verifies_hostname_and_ca(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            cert, key = root / 'server.crt', root / 'server.key'
            ca, ca_key, csr = root / 'ca.crt', root / 'ca.key', root / 'server.csr'
            commands = [
                ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(ca_key), '-out', str(ca), '-days', '1', '-subj', '/CN=Test CA'],
                ['openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(key), '-out', str(csr), '-subj', '/CN=memory.test'],
            ]
            extensions = root / 'extensions'
            extensions.write_text('subjectAltName=DNS:memory.test\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n')
            commands.append(['openssl', 'x509', '-req', '-in', str(csr), '-CA', str(ca), '-CAkey', str(ca_key), '-CAcreateserial', '-out', str(cert), '-days', '1', '-extfile', str(extensions)])
            for command in commands:
                subprocess.run(command, check=True, capture_output=True)
            received = []
            selected_model = 'family/model+variant'
            artifacts = {'index.json': b'{"fixture":true}', 'compact.pack': b'fixture-only-pack'}
            offer = {'schema': 1, 'lease': 'b' * 64, 'expires': int(time.time()) + 300,
                     'recipient': 'test', 'model': selected_model, 'key': 'c' * 64,
                     'authorized_view': 'd' * 64,
                     'records': [{'namespace': 'n', 'id': 'r', 'revision': '1'}],
                     'artifacts': [{'name': name, 'bytes': len(data),
                                    'sha256': hashlib.sha256(data).hexdigest()}
                                   for name, data in artifacts.items()]}

            class Handler(http.server.BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def respond(self, body):
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def do_GET(self):
                    received.append((self.path, self.headers.get('Host')))
                    path = urllib.parse.urlsplit(self.path).path
                    if path == '/v1/native/bootstrap':
                        body = json.dumps({'schema': 1, 'recipient': 'test', 'model': 'test',
                                           'model_config_sha256': 'a' * 64}).encode()
                    else:
                        body = artifacts[path.rsplit('/', 1)[-1]]
                    self.respond(body)

                def do_POST(self):
                    received.append((self.path, self.headers.get('Host')))
                    self.rfile.read(int(self.headers.get('Content-Length', '0')))
                    body = offer if urllib.parse.urlsplit(self.path).path.endswith('/select') else {'approved': True}
                    self.respond(json.dumps(body).encode())

            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_port
                def connect(host, trusted=True):
                    command = [args.launcher, '--root', str(root / host), 'connect',
                               f'https://{host}:{port}', '--connect-address', f'127.0.0.1:{port}']
                    if trusted:
                        command += ['--ca-file', str(ca)]
                    return subprocess.run(command, input=b'test-only-token', capture_output=True, timeout=20)
                good = connect('memory.test')
                self.assertEqual(good.returncode, 0, good.stderr.decode())
                self.assertNotEqual(connect('wrong.test').returncode, 0)
                self.assertNotEqual(connect('memory.test', trusted=False).returncode, 0)
                self.assertEqual(received, [('/v1/native/bootstrap', f'memory.test:{port}')])
                received.clear()
                command = [args.launcher, '--root', str(root / 'memory.test'), 'fetch-memory',
                           'fixture query', '--recipient', 'test', '--model', selected_model]
                fetched = subprocess.run(command, capture_output=True, timeout=20)
                self.assertEqual(fetched.returncode, 0, fetched.stderr.decode())
                expected_paths = ['/v1/native/select',
                                  f'/v1/native/leases/{offer["lease"]}/index.json',
                                  f'/v1/native/leases/{offer["lease"]}/compact.pack',
                                  f'/v1/native/leases/{offer["lease"]}/approve']
                self.assertEqual([urllib.parse.urlsplit(p).path for p, _ in received], expected_paths)
                for path, host in received:
                    self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(path).query),
                                     {'model': [selected_model]})
                    self.assertEqual(host, f'memory.test:{port}')
                received.clear()
                reused = subprocess.run(command, capture_output=True, timeout=20)
                self.assertEqual(reused.returncode, 0, reused.stderr.decode())
                self.assertEqual([urllib.parse.urlsplit(p).path for p, _ in received],
                                 [expected_paths[0], expected_paths[-1]])
                for path, _ in received:
                    self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(path).query),
                                     {'model': [selected_model]})
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main(argv=[__file__] + remaining)
