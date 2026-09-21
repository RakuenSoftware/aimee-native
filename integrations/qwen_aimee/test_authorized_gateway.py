"""Authorization transitions through real Go readers and the Unix read gateway.

The upstream here is a deterministic protocol fixture, not a live Aimee policy
owner. It lets us change a grant *during* an upstream read without timing races.
Set AIMEE_IMAGE_READER and AIMEE_FIXTURE_ISSUER to the built research binaries.
"""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import shutil
import signal
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from aimee_client import AimeeError, AimeeRequestRejected
from gateway_client import ReadGatewayClient, UnixHTTP
from local_first import LocalFirstClient
from local_image import AimeeImageClient


@unittest.skipUnless(os.environ.get('AIMEE_IMAGE_READER') and
                     os.environ.get('AIMEE_FIXTURE_ISSUER'), 'set reader and fixture issuer')
class AuthorizedGatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aimee-auth-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reader = os.environ['AIMEE_IMAGE_READER']
        self.issuer = os.environ['AIMEE_FIXTURE_ISSUER']
        self.source, self.image = self.root/'source', self.root/'image'
        self.grant, self.gateway_grant = self.root/'local.json', self.root/'gateway.json'
        self.public = self.root/'public.hex'
        self.records = [dict(namespace='general', id=str(i), revision='v1',
                             scope={'type':'global', 'value':'_global'}, key=key,
                             content=content, confidence=1, lifecycle='active',
                             kind='fact', tier='L3')
                        for i, key, content in [(1,'drink','drink oolong'), (2,'city','city Lima')]]
        self.until = (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        self.payload = {'status':'ok', 'facts':[{'id':'1','content':'drink oolong'}],
                        'windows':[], 'active_context_missing':False}
        self.contract = dict(query='drink', limit=2, authority='test', grants=[],
                             valid_until=self.until, response=self.payload,
                             dependencies=[{k:self.records[0][k] for k in ('namespace','id','revision')}])
        changes = self.root/'changes.json'
        changes.write_text(json.dumps(dict(namespace='general',kind='general',generation=1,
                                          records=self.records, source='test fixture',
                                          coverage=['facts'], read_contracts=[self.contract])))
        self.view = self.cli('build','--root',str(self.source),'--input',str(changes))['view']
        self.cli('publish','--root',str(self.source),'--view',self.view)
        self.binding = self.issue(self.grant)
        shutil.copyfile(self.grant,self.gateway_grant)
        self.cli('compile-authorized','--root',str(self.source),'--output-root',str(self.image),
                 *self.auth_args(self.grant))
        self.upstream_calls = []
        self.upstream_hook = lambda: None
        self.upstream_payload = self.payload
        self.echo_restriction = getattr(self, "restricted", False)
        self.thread_error = None
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                try:
                    body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    fixture.upstream_calls.append((self.path,body))
                    fixture.upstream_hook()
                    payload = dict(fixture.upstream_payload)
                    if fixture.echo_restriction:
                        payload["restriction"] = body.get("restriction")
                    raw = json.dumps(payload).encode()
                    self.send_response(200)
                    self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except Exception as exc:
                    fixture.thread_error = exc

        self.upstream_path = self.root/'upstream.sock'
        self.upstream = socketserver.UnixStreamServer(str(self.upstream_path),Handler)
        thread = threading.Thread(target=self.upstream.serve_forever,kwargs={'poll_interval':0.01})
        thread.start()
        def close_upstream():
            self.upstream.shutdown()
            thread.join(timeout=5)
            self.upstream.server_close()
        self.addCleanup(close_upstream)
        self.gateway_path = self.root/'gateway.sock'
        log = open(self.root/'gateway.log','w+')
        self.addCleanup(log.close)
        gateway_command = [os.environ['RUST_QWEN'], 'gateway'] if os.environ.get('RUST_QWEN') else [
            sys.executable,str(Path(__file__).with_name('read_gateway.py'))]
        if getattr(self, "restricted", False):
            gateway_command += ["--upstream-namespace", "general"]
        self.gateway = subprocess.Popen([*gateway_command,
            '--socket',str(self.gateway_path),'--upstream-unix',str(self.upstream_path),
            '--image-reader',self.reader,'--memory-image',str(self.image),
            *self.auth_args(self.gateway_grant)],stdout=log,stderr=log,start_new_session=True)
        self.addCleanup(self.stop_gateway)
        deadline = time.monotonic()+10
        while not self.gateway_path.exists():
            if self.gateway.poll() is not None or time.monotonic()>deadline:
                log.seek(0)
                self.fail('gateway did not start: '+log.read())
            time.sleep(0.01)
        self.remote = ReadGatewayClient(self.gateway_path,expected_authorization=self.binding)
        self.remote.begin_request()

    def stop_gateway(self):
        try:os.killpg(self.gateway.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        if self.gateway.poll() is None:
            try:self.gateway.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.gateway.kill()
                self.gateway.wait()

    def cli(self,*args):
        raw = subprocess.check_output([self.reader,*args])
        return json.loads(raw) if raw else None

    def auth_args(self,path):
        return ['--authorization',str(path),'--authority-key',str(self.public),
                '--subject','test-model','--policy-epoch','test-1']

    def issue(self,path,active=True,records=None,expired=False):
        # Test control plane only; no keys or issuer enter a model image.
        plan = self.root/'plan.json'
        until = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat() if expired else self.until
        plan.write_text(json.dumps(dict(
            authorization=dict(version=1,id='test-grant',subject='test-model',
                               policy_epoch='test-1',source_view=self.view,active=active,
                               valid_until=until,grants=[]),
            records=self.records if records is None else records,
            reads=[self.contract] if records is None else [])))
        staged = path.with_suffix('.pending')
        digest = subprocess.check_output([self.issuer,'--input',str(plan),'--output',str(staged),
                                          '--key',str(self.root/'private.key'),
                                          '--public-key',str(self.public)],text=True).strip()
        os.replace(staged,path)
        return digest

    def local_first(self):
        if os.environ.get('RUST_QWEN'):
            client = RustReadClient(self)
        else:
            local = AimeeImageClient(self.reader,self.image,authorization=self.grant,
                                     authority_key=self.public,subject='test-model',policy_epoch='test-1')
            client = LocalFirstClient(local,self.remote,'test')
        self.addCleanup(client.close)
        client.begin_request()
        self.assertEqual(client.search('drink',2),self.payload)
        self.assertEqual(self.upstream_calls,[])
        return client

    def test_local_revocation_cannot_escape_through_stale_remote_grant(self):
        client = self.local_first()
        self.issue(self.grant,active=False)
        # The remote guard deliberately still has the old active decision.
        self.remote.begin_request()
        with self.assertRaises(AimeeRequestRejected):client.search('drink',2)
        with self.assertRaises(AimeeError):client.search('new query',2)
        with self.assertRaises(AimeeRequestRejected):client.begin_request()
        self.assertFalse(client.request_authorized)
        self.assertEqual(self.upstream_calls,[])

    def test_narrowed_grant_requires_new_image_and_session(self):
        client = self.local_first()
        self.issue(self.grant,records=[self.records[1]])
        with self.assertRaises(AimeeRequestRejected):client.search('drink',2)
        with self.assertRaises(AimeeRequestRejected):client.begin_request()
        self.assertEqual(self.upstream_calls,[])

    def test_expired_local_grant_cannot_fall_back(self):
        client = self.local_first()
        self.issue(self.grant,expired=True)
        with self.assertRaises(AimeeRequestRejected):client.search('drink',2)
        self.assertEqual(self.upstream_calls,[])

    def test_remote_revocation_cannot_escape_through_stale_local_hit(self):
        client = self.local_first()
        self.issue(self.gateway_grant,active=False)
        with self.assertRaises(AimeeRequestRejected):client.search('novel query',2)
        # Local still holds its original valid file and covered drink response.
        with self.assertRaises(AimeeError):client.search('drink',2)
        self.assertFalse(client.request_authorized)
        self.assertFalse(client.local_ready)
        self.assertEqual(self.upstream_calls,[])

    def test_revocation_during_upstream_read_blocks_response(self):
        self.upstream_hook = lambda:self.issue(self.gateway_grant,active=False)
        with self.assertRaises(AimeeRequestRejected):self.remote.search('novel query',2)
        self.assertIsNone(self.thread_error)
        self.assertEqual(len(self.upstream_calls),1)
        with self.assertRaises(AimeeRequestRejected):self.remote.search('again',2)
        self.assertEqual(len(self.upstream_calls),1)

    def test_mixed_unauthorized_response_is_atomic_and_does_not_poison_reader(self):
        self.upstream_payload = dict(self.payload,facts=self.payload['facts']+[
            {'id':'99','content':'secret-canary-not-authorized'}])
        connection = UnixHTTP(str(self.gateway_path),timeout=10)
        self.addCleanup(connection.close)
        connection.request('POST','/search',json.dumps(dict(query='mixed',limit=2,authorization=self.binding)),
                           {'Content-Type':'application/json'})
        response = connection.getresponse()
        raw = response.read()
        self.assertEqual(response.status,403)
        self.assertNotIn(b'canary',raw)
        self.assertNotIn(b'oolong',raw)
        self.upstream_payload = self.payload
        result = self.remote.search('valid again',2)
        if getattr(self, 'restricted', False):
            self.assertEqual(result.pop('restriction')['authorization'], self.binding)
        self.assertEqual(result,self.payload)
        self.assertEqual(len(self.upstream_calls),2)


class RustReadClient:
    """Test driver only. All decisions and transport execute in the Rust binary."""
    def __init__(self,fixture):
        self.process=subprocess.Popen([os.environ['RUST_QWEN'],'read-check',
            '--image-reader',fixture.reader,'--memory-image',str(fixture.image),
            '--read-gateway',str(fixture.gateway_path),'--read-authority','test',
            *fixture.auth_args(fixture.grant)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            text=True,start_new_session=True)
        self.request_authorized=False
        self.local_ready=False
    def call(self,request):
        import select
        self.process.stdin.write(json.dumps(request)+'\n');self.process.stdin.flush()
        if not select.select([self.process.stdout],[],[],10)[0]:raise AimeeError('Rust reader timed out')
        raw=self.process.stdout.readline()
        if not raw:raise AimeeError('Rust reader closed')
        envelope=json.loads(raw);self.request_authorized=envelope['admitted'];self.local_ready=envelope['local_ready']
        result=envelope['result']
        if result.get('error'):
            raise (AimeeRequestRejected if result.get('denied') else AimeeError)('read rejected')
        return result
    def begin_request(self):return self.call({'op':'begin'})
    def search(self,query,limit):return self.call({'op':'search','query':query,'limit':limit})
    def close(self):
        try:os.killpg(self.process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        self.process.wait(timeout=5)
        self.process.stdin.close();self.process.stdout.close()


@unittest.skipUnless(os.environ.get('RUST_QWEN'), 'Rust native identity path')
class NativeIdentityTests(AuthorizedGatewayTests):
    def test_local_and_remote_native_identity_match(self):
        client = self.local_first()
        local = client.call({'op':'native_search','query':'drink','limit':2})
        self.assertEqual(local['facts'][0]['memory_ref'], dict(namespace='general',id='1',revision='v1'))
        remote = client.call({'op':'native_search','query':'unpublished paraphrase','limit':2})
        self.assertEqual(remote,local)
        self.assertEqual(len(self.upstream_calls),1)

    def test_forged_native_identity_is_rejected(self):
        client = self.local_first()
        self.upstream_payload = json.loads(json.dumps(self.payload))
        self.upstream_payload['facts'][0]['memory_ref'] = {'namespace':'foreign','id':'1','revision':'v1'}
        with self.assertRaises(AimeeRequestRejected):
            client.call({'op':'native_search','query':'uncached','limit':2})
        self.assertFalse(client.request_authorized)

    def test_native_read_after_revocation_is_terminal(self):
        client = self.local_first()
        self.issue(self.grant,active=False)
        with self.assertRaises(AimeeRequestRejected):
            client.call({'op':'native_search','query':'drink','limit':2})
        self.assertEqual(self.upstream_calls,[])


    def test_native_transport_failure_uses_guarded_remote_resolution(self):
        client = self.local_first()
        child_path = Path(f'/proc/{client.process.pid}/task/{client.process.pid}/children')
        children = [int(x) for x in child_path.read_text().split()]
        self.assertEqual(len(children), 1)
        os.kill(children[0], signal.SIGTERM)
        result = client.call({'op':'native_search','query':'drink','limit':2})
        self.assertEqual(result['facts'][0]['memory_ref']['namespace'], 'general')
        self.assertEqual(len(self.upstream_calls),1)
        self.assertFalse(client.local_ready)



@unittest.skipUnless(os.environ.get('RUST_QWEN'), 'Rust restricted gateway required')
class RestrictedGatewayTests(AuthorizedGatewayTests):
    restricted = True

    def test_restriction_comes_from_grant(self):
        result = self.remote.search('novel query', 2)
        restriction = self.upstream_calls[-1][1]['restriction']
        self.assertEqual(restriction, dict(version=1, namespace='general', authorization=self.binding, ids=[1,2]))
        self.assertEqual(result['facts'], self.payload['facts'])

    def test_old_upstream_cannot_silently_ignore_restriction(self):
        self.echo_restriction = False
        with self.assertRaises(AimeeRequestRejected): self.remote.search('query',2)

    def test_explicit_restricted_empty_is_success(self):
        self.upstream_payload = dict(self.payload, facts=[])
        self.assertEqual(self.remote.search('no match',2)['facts'], [])

    def test_restriction_is_not_a_license_to_release_other_content(self):
        self.upstream_payload = dict(self.payload, facts=[{'id':'99','content':'withheld'}])
        with self.assertRaises(AimeeRequestRejected): self.remote.search('query',2)

if __name__ == '__main__':
    unittest.main(verbosity=2)
