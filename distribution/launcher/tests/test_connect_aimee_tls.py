"""End-to-end thin-client primitive access against a disposable mTLS server.

Usage: python3 test_connect_aimee_tls.py /path/to/aimee-native
"""

import json
import os
import pathlib
import ssl
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

if len(sys.argv) != 2:
    raise SystemExit("usage: test_connect_aimee_tls.py /path/to/aimee-native")
LAUNCHER = sys.argv[1]

def cert(base, name, extra, authority=None):
    key = base / f"{name}.key"
    crt = base / f"{name}.crt"
    command = ["openssl", "req", "-newkey", "rsa:2048", "-nodes", "-subj", f"/CN={name}",
               "-keyout", str(key)]
    if authority is None:
        subprocess.run(command + ["-x509", "-days", "1", "-addext", "basicConstraints=critical,CA:TRUE",
                                  "-out", str(crt)], check=True, capture_output=True)
    else:
        csr = base / f"{name}.csr"
        subprocess.run(command + ["-out", str(csr)], check=True, capture_output=True)
        extension = base / f"{name}.ext"
        extension.write_text(extra + "\n")
        subprocess.run(["openssl", "x509", "-req", "-in", str(csr), "-CA", str(authority[1]),
                        "-CAkey", str(authority[0]), "-CAcreateserial", "-days", "1", "-out", str(crt),
                        "-extfile", str(extension)], check=True, capture_output=True)
    return key, crt

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if (self.path != "/v1/native/primitive"
                or self.headers.get("Authorization") != "Bearer enrolled-token"
                or not self.connection.getpeercert()):
            self.send_error(403)
            return
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if (request.get("store") != "user" or request.get("task_hint") not in
                ("native memory connection", "test query")):
            self.send_error(400)
            return
        records = [] if request["task_hint"] == "native memory connection" else [
            {"id": 7, "content": "fixture fact", "version": {"schema_version": 1,
             "owner_id": "00000000-0000-0000-0000-000000000001",
             "record_id": "7", "record_revision": "3"}}]
        body = json.dumps({"schema": 1, "records": records}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

with tempfile.TemporaryDirectory() as tmp:
    base = pathlib.Path(tmp)
    ca_key, ca_crt = cert(base, "test-ca", "")
    server_key, server_crt = cert(base, "localhost", "subjectAltName=DNS:localhost\nextendedKeyUsage=serverAuth", (ca_key, ca_crt))
    client_key, client_crt = cert(base, "thin-client", "extendedKeyUsage=clientAuth", (ca_key, ca_crt))
    server = HTTPServer(("127.0.0.1", 0), Handler)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(str(server_crt), str(server_key))
    tls.verify_mode = ssl.CERT_REQUIRED
    tls.load_verify_locations(str(ca_crt))
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    home = base / "aimee"
    (home / "tls").mkdir(parents=True)
    endpoint = f"https://localhost:{server.server_port}"
    (home / "remote.conf").write_text(endpoint + "\nenrolled-token\n")
    (home / "remote-ca.pem").write_bytes(ca_crt.read_bytes())
    (home / "tls/client.crt").write_bytes(client_crt.read_bytes())
    (home / "tls/client.key").write_bytes(client_key.read_bytes())
    for name in ("remote.conf", "tls/client.crt", "tls/client.key"):
        os.chmod(home / name, 0o600)
    root = base / "plugin"
    command = [LAUNCHER, "--root", str(root), "connect-aimee", "--aimee-home", str(home)]
    environment = dict(os.environ, NO_PROXY="localhost,127.0.0.1", no_proxy="localhost,127.0.0.1")
    done = subprocess.run(command, text=True, capture_output=True, env=environment)
    assert done.returncode == 0, (done.stdout, done.stderr)
    assert json.loads((root / "config.json").read_text())["endpoint"].rstrip("/") == endpoint
    assert not (root / "native-profile.json").exists()
    fetched = subprocess.run([LAUNCHER, "--root", str(root), "fetch-primitive", "test query"],
                             text=True, capture_output=True, env=environment)
    assert fetched.returncode == 0, (fetched.stdout, fetched.stderr)
    assert json.loads(fetched.stdout) == {"records": 1, "schema": 1}
    os.chmod(home / "tls/client.key", 0o644)
    refused = subprocess.run(command, text=True, capture_output=True, env=environment)
    assert refused.returncode != 0
    print("TLS thin-client identity accepted; exposed key refused")
    server.shutdown()
    thread.join(timeout=3)
    server.server_close()
