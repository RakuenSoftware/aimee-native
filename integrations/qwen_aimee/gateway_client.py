"""Model-side read client with no Aimee credentials or arbitrary proxy URL."""
import http.client
import json
import socket
from aimee_client import AimeeError, AimeeRequestRejected

class UnixHTTP(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.host)

class ReadGatewayClient:
    def __init__(self,path,timeout=60,expected_authorization=None):
        self.path=str(path);self.timeout=timeout;self.authorization_id=expected_authorization

    def _read(self,path,body):
        connection=UnixHTTP(self.path,timeout=self.timeout)
        try:
            connection.request('POST',path,body=json.dumps(body),headers={'Content-Type':'application/json'})
            response=connection.getresponse();result=json.loads(response.read())
            if response.status in (400,401,403):
                raise AimeeRequestRejected('authorized read gateway rejected request')
            if response.status!=200 or not isinstance(result,dict):
                raise AimeeError('authorized read gateway rejected request')
            return result
        except (OSError,ValueError,http.client.HTTPException) as exc:
            raise AimeeError('read gateway failed: '+type(exc).__name__) from None
        finally:connection.close()

    def begin_request(self):
        identity=self._read('/identity',{})['authorization']
        if self.authorization_id is not None and identity!=self.authorization_id:
            raise AimeeRequestRejected('gateway authorization changed; create a new session')
        self.authorization_id=identity

    def search(self,query,limit):
        if self.authorization_id is None:self.begin_request()
        result=self._read('/search',{'query':query,'limit':limit,'authorization':self.authorization_id})
        if not isinstance(result.get('facts'),list):raise AimeeError('gateway response has no facts')
        return result

    def close(self):pass
