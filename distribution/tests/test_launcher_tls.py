"""Exercise the production launcher's private-address TLS connection, without GPU."""
import argparse
import http.server
import json
import pathlib
import ssl
import subprocess
import tempfile
import threading
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

            class Handler(http.server.BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def do_GET(self):
                    received.append((self.path, self.headers.get('Host')))
                    body = json.dumps({'schema': 1, 'recipient': 'test', 'model': 'test',
                                       'model_config_sha256': 'a' * 64}).encode()
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

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
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main(argv=[__file__] + remaining)
