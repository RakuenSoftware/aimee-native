"""Direct, read-only transport to Aimee's existing memory.search API."""
import http.client
import urllib.parse
import json
from pathlib import Path
import ssl
import urllib.request


class AimeeError(RuntimeError):
    pass


class AimeeRequestRejected(AimeeError):
    """A complete, rejected request; transport framing remains synchronized."""
    pass


class AimeeClient:
    def __init__(self, config, ca_file, timeout=60, cert_file=None, key_file=None, keepalive=False):
        lines = Path(config).read_text().splitlines()
        if len(lines) < 2 or not lines[0].startswith("https://") or not lines[1].strip():
            raise ValueError("expected HTTPS URL and bearer in private config")
        self.url = lines[0].strip().rstrip("/")
        self._bearer = lines[1].strip()
        self.context = ssl.create_default_context(cafile=str(ca_file))
        if bool(cert_file) != bool(key_file):
            raise ValueError("both client certificate and key are required")
        if cert_file:
            self.context.load_cert_chain(str(cert_file), str(key_file))
        self.timeout = timeout
        self.keepalive = keepalive
        self.connection = None
        self.connections_opened = 0

    def search(self, query, limit):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("nonempty query required")
        if type(limit) is not int or not 1 <= limit <= 32:
            raise ValueError("Aimee limit must be in 1..32")
        request = urllib.request.Request(
            self.url + "/v1/memory/search",
            data=json.dumps({"keywords": [query], "limit": limit}).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self._bearer})
        try:
            if self.keepalive:
                url = urllib.parse.urlsplit(request.full_url)
                if self.connection is None or self.connection.sock is None:
                    self.connection = http.client.HTTPSConnection(url.hostname, url.port, timeout=self.timeout, context=self.context)
                    self.connections_opened += 1
                self.connection.request("POST", url.path, body=request.data, headers=dict(request.header_items()))
                response = self.connection.getresponse()
                body = response.read()
                if response.status != 200:
                    raise AimeeError("memory.search HTTP status rejected")
                payload = json.loads(body)
            else:
                with urllib.request.urlopen(request, context=self.context, timeout=self.timeout) as response:
                    payload = json.load(response)
        except Exception as exc:
            self.close()
            # Do not include request headers, bearer, or HTTP response bodies.
            raise AimeeError("memory.search transport failed: " + type(exc).__name__) from None
        if not isinstance(payload, dict) or payload.get("error"):
            raise AimeeError("memory.search returned an error")
        if not isinstance(payload.get("facts"), list):
            raise AimeeError("memory.search response has no facts array")
        return payload  # No ranking, filtering, or interpretation here.

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

class AimeeUnixClient:
    """Read-only same-appliance transport; authorization still belongs to Aimee.

    Only the credential/gateway identity may access the authority's Unix socket.
    Model processes receive the separately guarded gateway socket instead.
    """
    def __init__(self, path, timeout=60):
        self.path, self.timeout = str(path), timeout

    def search(self, query, limit):
        if not isinstance(query, str) or not query.strip() or type(limit) is not int or not 1 <= limit <= 32:
            raise ValueError('valid query and limit required')
        from gateway_client import UnixHTTP
        connection = UnixHTTP(self.path, timeout=self.timeout)
        try:
            connection.request('POST', '/v1/memory/search',
                               json.dumps({'keywords': [query], 'limit': limit}),
                               {'Content-Type': 'application/json'})
            response = connection.getresponse()
            result = json.loads(response.read())
            if response.status != 200 or not isinstance(result, dict) or result.get('status') != 'ok' or not isinstance(result.get('facts'), list):
                raise AimeeError('Aimee read rejected')
            return result
        except (OSError, ValueError, http.client.HTTPException) as exc:
            raise AimeeError('Aimee Unix read failed: ' + type(exc).__name__) from None
        finally:
            connection.close()

    def close(self):
        pass
