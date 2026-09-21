"""Persistent local connection to Aimee's sparse image reader.

The Go memory module owns lookup, scope and validity. This transport neither
ranks facts nor contacts a remote Aimee service. Each model request pins a view.
"""
import json
import os
from pathlib import Path
import select
import subprocess

from aimee_client import AimeeError, AimeeRequestRejected


class AimeeImageClient:
    def __init__(self, executable, root, scopes=(), view=None, timeout=30, authorization=None, authority_key=None, subject=None, policy_epoch=None, unsafe_research=False):
        command = [str(Path(executable).resolve()), "serve", "--root", str(Path(root).resolve()),
                   "--scopes", ",".join(scopes)]
        if authorization:
            if scopes or not all((authority_key, subject, policy_epoch)):
                raise ValueError("authorization requires trusted key/subject/epoch and excludes caller scopes")
            command += ["--authorization", str(authorization), "--authority-key", str(authority_key),
                        "--subject", subject, "--policy-epoch", policy_epoch]
        elif unsafe_research:
            command += ["--unsafe-research"]
        else:
            raise ValueError("model images require explicit Aimee authorization")
        self.authorization_id = None
        if view:
            command += ["--view", view]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        text=False, bufsize=0)
        self.timeout = timeout
        self.view = None

    def _call(self, request):
        try:
            if self.process.poll() is not None:
                raise AimeeError("local memory reader exited")
            self.process.stdin.write(json.dumps(request).encode() + b"\n")
            self.process.stdin.flush()
            # Read one response without TextIO prefetch hiding bytes from select.
            data = bytearray()
            import time
            deadline = time.monotonic() + self.timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                    raise AimeeError("local memory reader timed out")
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise AimeeError("local memory reader closed its response")
                data.extend(chunk)
                if len(data) > 16 << 20:
                    raise AimeeError("local memory response exceeds transport capacity")
                if b"\n" in chunk:
                    break
            response = json.loads(data)
            if response.get("error"):
                raise AimeeRequestRejected("local memory read rejected")
            return response
        except (OSError, ValueError) as exc:
            self.close()
            raise AimeeError("local memory transport failed: " + type(exc).__name__) from None
        except AimeeRequestRejected:
            # A complete denial must not poison later authorized requests.
            raise
        except AimeeError:
            # A timeout cannot leave a late response queued for a different call.
            self.close()
            raise

    def begin_request(self):
        result = self._call({"op": "pin"})
        self.view = result["view"]
        self.authorization_id = result.get("authorization")
        return self.view

    def authorize_response(self, response):
        return self._call({"op": "authorize_response", "response": response})

    def recall(self, query, limit, authority):
        if self.view is None:
            raise AimeeError("local memory requires a pinned request")
        result = self._call({"op": "recall", "query": query, "limit": limit, "authority": authority})
        if result["view"] != self.view:
            raise AimeeError("local memory generation changed inside request")
        return result

    def search(self, query, limit):
        if self.view is None:
            raise AimeeError("local memory requires a pinned request")
        result = self._call({"op": "search", "query": query, "limit": limit})
        if result["view"] != self.view:
            raise AimeeError("local memory generation changed inside request")
        facts = []
        for record in result["records"]:
            fact = dict(record)
            fact["source_id"] = record["id"]
            fact["id"] = record["namespace"] + ":" + record["id"]
            facts.append(fact)
        return {"facts": facts, "windows": [], "active_context_missing": False,
                "local_image": {k: v for k, v in result.items() if k != "records"}}

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        for pipe in (self.process.stdin, self.process.stdout):
            if pipe and not pipe.closed:
                pipe.close()
