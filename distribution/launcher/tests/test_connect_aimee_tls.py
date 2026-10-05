"""End-to-end thin-client primitive access against a disposable mTLS server.

Usage: python3 test_connect_aimee_tls.py /path/to/aimee-native
"""

import json
import os
import pathlib
import ssl
import socket
import subprocess
import sys
import tempfile
import threading
import time
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
    revision = 3
    reject = False
    token = "enrolled-token"
    client_cn = "thin-client"
    def do_POST(self):
        peer = self.connection.getpeercert()
        common_name = dict(item[0] for item in peer.get("subject", ())).get("commonName") if peer else None
        if (self.reject or self.path != "/v1/native/primitive"
                or self.headers.get("Authorization") != "Bearer " + self.token
                or common_name != self.client_cn):
            self.send_error(403)
            return
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if (request.get("store") != "user" or request.get("task_hint") not in
                ("native memory connection", "test query", "broker query")):
            self.send_error(400)
            return
        records = [] if request["task_hint"] == "native memory connection" else [
            {"id": 7, "content": "fixture fact", "version": {"schema_version": 1,
             "owner_id": "00000000-0000-0000-0000-000000000001",
             "record_id": "7", "record_revision": str(self.revision)}}]
        if request["task_hint"] == "broker query":
            records.append({"id": 8, "content": "second fixture fact", "version": {
                "schema_version": 1, "owner_id": "00000000-0000-0000-0000-000000000001",
                "record_id": "8", "record_revision": "1"}})
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
    # Aimee may enroll through a server IP even when the pinned certificate
    # names only localhost. This matches the real self-hosted appliance case.
    endpoint = f"https://127.0.0.1:{server.server_port}"
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
    connected = json.loads((root / "config.json").read_text())
    assert connected["endpoint"].rstrip("/") == endpoint
    assert connected["thinclient_home"] == str(home)
    assert not pathlib.Path(connected["token_file"]).exists()
    assert not (root / "credentials").exists()
    assert not (root / "native-profile.json").exists()
    Handler.token = "renewed-token"
    (home / "remote.conf").write_text(endpoint + "\nrenewed-token\n")
    os.chmod(home / "remote.conf", 0o600)
    renewed_key, renewed_crt = cert(base, "thin-client-renewed",
        "extendedKeyUsage=clientAuth", (ca_key, ca_crt))
    (home / "tls/client.crt").write_bytes(renewed_crt.read_bytes())
    (home / "tls/client.key").write_bytes(renewed_key.read_bytes())
    os.chmod(home / "tls/client.crt", 0o600)
    os.chmod(home / "tls/client.key", 0o600)
    Handler.client_cn = "thin-client-renewed"
    fetched = subprocess.run([LAUNCHER, "--root", str(root), "fetch-primitive", "test query"],
                             text=True, capture_output=True, env=environment)
    assert fetched.returncode == 0, (fetched.stdout, fetched.stderr)
    assert json.loads(fetched.stdout) == {"records": 1, "schema": 1}
    _, wrong_ca = cert(base, "untrusted-ca", "")
    (home / "remote-ca.pem").write_bytes(wrong_ca.read_bytes())
    rejected = subprocess.run([LAUNCHER, "--root", str(root), "fetch-primitive", "test query"],
                              text=True, capture_output=True, env=environment)
    assert rejected.returncode != 0, (rejected.stdout, rejected.stderr)
    (home / "remote-ca.pem").write_bytes(ca_crt.read_bytes())
    connection = json.loads((root / "config.json").read_text())
    memory = pathlib.Path(connection["memory_root"])
    catalog = memory / "catalog.json"
    catalog.write_text(json.dumps({"recipient": "test-recipient", "model_config_sha256": "a" * 64,
                                   "publications": {}, "selections": []}))
    compiler = base / "compile.py"
    compiler.write_text("""import argparse,json,pathlib,sys
p=argparse.ArgumentParser();p.add_argument('--output');p.add_argument('--identity');p.add_argument('--key');a=p.parse_args()
request=json.load(sys.stdin)
assert len(request['identity']['records']) == len(request['response']['facts']) == 2
out=pathlib.Path(a.output);out.mkdir()
(out/'index.json').write_text(json.dumps({'version':1,'model':a.identity,'native_layout':True,'records':{a.key:{'tokens':[1,2]}}}))
(out/'compact.pack').write_bytes(bytes(4096)+b'bank')
""")
    serving = root / "serving.json"
    serving.write_text(json.dumps({"recipient": "test-recipient", "catalog": str(catalog),
        "selection_socket": str(memory / "selection.sock"),
        "control_socket": str(memory / "control.sock"),
        "local_preparation": {"compiler": [sys.executable, str(compiler)],
            "model_config_sha256": "a" * 64, "runtime_profile": "test-vllm",
            "encoding_revision": "one", "position_policy": "negative", "limit_tokens": 1024}}))
    control = socket.socket(socket.AF_UNIX)
    control.bind(str(memory / "control.sock"))
    control.listen()
    state = {"value": "active", "generation": 0, "done": False}
    def control_loop():
        while not state["done"]:
            try:
                peer, _ = control.accept()
            except OSError:
                return
            with peer:
                request = json.loads(peer.makefile().readline())
                if request["op"] == "withdraw":
                    state["generation"] += 1
                    state["value"] = "paused"
                elif request["op"] == "refresh":
                    state["value"] = "active"
                peer.sendall((json.dumps({"state": state["value"],
                    "generation": state["generation"]}) + "\n").encode())
    control_thread = threading.Thread(target=control_loop, daemon=True)
    control_thread.start()
    broker = subprocess.Popen([LAUNCHER, "--root", str(root), "memory-agent",
        "--serving", str(serving), "--model", "gemma", "--disk-budget", "1048576"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
    try:
        selection = memory / "selection.sock"
        for _ in range(100):
            if selection.exists():
                break
            assert broker.poll() is None, broker.stderr.read().decode()
            time.sleep(0.05)
        assert selection.exists()
        def select():
            with socket.socket(socket.AF_UNIX) as peer:
                peer.connect(str(selection))
                peer.sendall(b'{"query":"broker query"}\n')
                return json.loads(peer.makefile().readline())
        first = select()
        assert first.get("publication") and "error" not in first, first
        initial = json.loads(catalog.read_text())
        assert len(initial["selections"][0]["records"]) == 2
        Handler.revision = 4
        second = select()
        assert second.get("publication") != first["publication"], second
        assert len(json.loads(catalog.read_text())["selections"][0]["records"]) == 2
        Handler.reject = True
        denied = select()
        assert denied == {"error": "native_selection_unavailable"}, denied
        print("local broker activated both records, replaced changed revision, and denied revoked access")
    finally:
        broker.terminate()
        broker.communicate(timeout=5)
        state["done"] = True
        control.close()
        control_thread.join(timeout=1)
    os.chmod(home / "tls/client.key", 0o644)
    refused = subprocess.run(command, text=True, capture_output=True, env=environment)
    assert refused.returncode != 0
    print("TLS thin-client identity accepted; exposed key refused")
    server.shutdown()
    thread.join(timeout=3)
    server.server_close()
