"""Actual Aimee owner API admission/read-back, never a JSONL stand-in."""
import hashlib,http.client,json,socket
from pathlib import Path

class UnixHTTP(http.client.HTTPConnection):
    def __init__(self,path):super().__init__('localhost',timeout=60);self.path=path
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout);self.sock.connect(self.path)

class CanonicalStore:
    def __init__(self,receipt):
        self.identity=json.loads(Path(receipt).read_text())
        assert self.identity['private_experiment_instance'] is True
        assert self.identity['study']=='retained-transfer-20261011-r1'
        assert self.identity['data_root'].startswith('/mnt/pve/backup/aimee-experiments/retained-transfer-20261011-r1/')
        self.path=self.identity['http_socket']
        assert Path(self.path).is_socket()
        # Retrieval/embedding readiness is outside this exact-record study.
        # Preserve a degraded global report and test the required operations.
        self.ready=self.call('/v1/ready',accepted_statuses=(200,503))
        self.manifest=self.call('/v1/cli/manifest')
        encoded=json.dumps(self.manifest)
        assert 'memory.store' in encoded and 'memory.get' in encoded
        self.preflight=self.admit({'family_id':'readiness-probe','source_session':'store-preflight',
            'content':'Readiness probe, not a learned rule.',
            'content_sha256':hashlib.sha256(b'Readiness probe, not a learned rule.').hexdigest()})
    def call(self,route,body=None,accepted_statuses=(200,)):
        connection=UnixHTTP(self.path)
        try:
            connection.request('GET' if body is None else 'POST',route,
                body=None if body is None else json.dumps(body),headers={'Content-Type':'application/json'})
            response=connection.getresponse();data=response.read()
            if response.status not in accepted_statuses:raise RuntimeError({'status':response.status,'body':data.decode()})
            return json.loads(data)
        finally:connection.close()
    def admit(self,candidate):
        content=candidate['content'];sha=hashlib.sha256(content.encode()).hexdigest()
        assert sha==candidate['content_sha256']
        key='retained-transfer-20261011-r1/'+candidate['family_id']+'/'+sha
        response=self.call('/v1/memory/store',{'method':'memory.store','key':key,'content':content,'session_id':candidate['source_session']})
        assert response['status']=='ok'
        rid=str(response['id'])
        readback=self.call('/v1/memory/get',{'method':'memory.get','id':rid})
        assert readback['status']=='ok' and readback['memory']['content']==content
        return dict(candidate,canonical_admission='verified-store-and-readback',canonical_record_id=rid,
                    canonical_key=key,store_response=response,readback_response=readback)
