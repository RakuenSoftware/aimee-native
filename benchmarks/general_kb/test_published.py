"""Real Rust + Go integration. No model, grant files, or gateway in the reader path."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler
import socketserver
import threading

REPO = Path(__file__).resolve().parents[2]
READER = Path(os.environ.get('AIMEE_IMAGE_READER', REPO / '.local/bin/aimee-memory-image'))
ISSUER = Path(os.environ.get('AIMEE_FIXTURE_ISSUER', REPO / '.local/bin/aimee-issue-fixture'))
RUST = Path(os.environ.get('RUST_QWEN', REPO / 'target/debug/aimee-qwen'))


class PublishedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.active = self.root / 'active'
        self.image1 = self.publish('one', 'teal')
        self.active.symlink_to(self.image1, target_is_directory=True)
        self.proc = subprocess.Popen([
            str(RUST), 'read-check', '--memory-image', str(self.active),
            '--image-reader', str(READER), '--read-authority', 'test',
            '--read-gateway', str(self.root / 'nonexistent-gateway.sock'),
        ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.addCleanup(self.stop)

    def stop(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=5)
        self.proc.stdout.close()

    def cli(self, *args):
        output = subprocess.check_output([str(READER), *map(str, args)], text=True)
        return json.loads(output) if output else None

    def publish(self, name, value):
        private = self.root / name
        private.mkdir()
        row = dict(namespace='general', id='one', revision=name, scope=dict(type='global', value='_global'),
                   kind='fact', tier='L3', key='beacon color', content=value, lifecycle='active', confidence=1,
                   metadata={'internal': 'EXCLUDED_PRIVATE_METADATA'})
        withheld = dict(row, id='two', key='beacon secret', content='EXCLUDED_UNAUTHORIZED_CONTENT')
        change = dict(namespace='general', kind='general', generation=1, source='test', coverage=['facts'], records=[row, withheld])
        path = private / 'input.json'
        path.write_text(json.dumps(change))
        source = private / 'source'
        view = self.cli('build', '--root', source, '--input', path)['view']
        self.cli('publish', '--root', source, '--view', view)
        approval = dict(version=1, id=name, subject='recipient', policy_epoch='test', source_view=view,
                        active=True, valid_until=(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat(),
                        grants=[], reference_lookups=[dict(namespace='general', authority='test', mode='exact-key-v1')])
        plan = private / 'plan.json'
        plan.write_text(json.dumps(dict(authorization=approval, records=[row], reads=[])))
        subprocess.run([str(ISSUER), '--input', str(plan), '--output', str(private/'grant'),
                        '--key', str(private/'key'), '--public-key', str(private/'public')], check=True, stdout=subprocess.DEVNULL)
        image = self.root / (name + '-image')
        self.cli('compile-authorized', '--root', source, '--output-root', image,
                 '--authorization', private/'grant', '--authority-key', private/'public', '--subject', 'recipient', '--policy-epoch', 'test')
        # There is deliberately no usable grant or verifier available to reads.
        (private/'grant').unlink()
        (private/'public').unlink()
        return image

    def call(self, op, **kw):
        self.proc.stdin.write(json.dumps(dict(op=op, **kw)) + '\n')
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        self.assertTrue(line, 'reader exited')
        return json.loads(line)

    def read(self):
        return self.call('native_search', query='What is the beacon color?', limit=4)

    def test_local_hit_without_credentials_or_gateway(self):
        self.assertNotIn('error', self.call('begin')['result'])
        r = self.read()['result']
        self.assertEqual(r['facts'][0]['content'], 'teal')
        self.assertEqual(r['facts'][0]['memory_ref'], dict(namespace='general', id='one', revision='one'))
        for f in self.image1.rglob('*'):
            if f.is_file():
                self.assertNotIn(b'EXCLUDED_', f.read_bytes())
        self.assertFalse((self.image1/'AUTHORIZATION.json').exists())

    def test_new_generation_and_withdrawal(self):
        first = self.call('begin')['result']
        self.assertEqual(self.read()['result']['facts'][0]['content'], 'teal')
        image2 = self.publish('two', 'amber')
        replacement = self.root/'next'
        replacement.symlink_to(image2, target_is_directory=True)
        replacement.replace(self.active)
        # Existing request pins its generation; next request observes publication.
        self.assertEqual(self.read()['result']['facts'][0]['content'], 'teal')
        second = self.call('begin')['result']
        self.assertNotEqual(first, second)
        self.assertEqual(self.read()['result']['facts'][0]['content'], 'amber')
        self.active.unlink()
        self.assertIn('error', self.call('begin')['result'])
        self.assertIn('error', self.read()['result'])

    def test_missing_does_not_invent_local_answer(self):
        self.call('begin')
        r = self.call('native_search', query='beacon secret', limit=4)
        # Miss attempts the configured fallback, which is deliberately absent.
        self.assertIn('error', r['result'])

    def test_managed_install_update_cleanup_and_withdraw(self):
        self.stop()
        recipient = self.root/'recipient'
        first = self.cli('install-published', '--root', self.image1, '--output-root', recipient)
        self.proc = subprocess.Popen([
            str(RUST), 'read-check', '--memory-image', str(recipient),
            '--image-reader', str(READER), '--read-authority', 'test',
            '--read-gateway', str(self.root/'nonexistent-gateway.sock'),
        ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.call('begin')
        self.assertEqual(self.read()['result']['facts'][0]['content'], 'teal')
        image2 = self.publish('two', 'amber')
        second = self.cli('install-published', '--root', image2, '--output-root', recipient, '--expected', first['view'])
        self.assertEqual(second['removed_snapshots'], 1)
        self.assertEqual(self.read()['result']['facts'][0]['content'], 'teal')
        self.call('begin')
        self.assertEqual(self.read()['result']['facts'][0]['content'], 'amber')
        for f in recipient.rglob('*'):
            if f.is_file():
                self.assertNotIn(b'teal', f.read_bytes())
                self.assertNotIn(b'EXCLUDED_', f.read_bytes())
        self.cli('withdraw-published', '--root', recipient, '--expected', second['view'])
        self.assertEqual(list((recipient/'snapshots').iterdir()), [])
        self.assertIn('error', self.call('begin')['result'])
        self.assertIn('error', self.read()['result'])

    def test_local_replacement_keeps_independent_remote_fallback(self):
        calls = []
        wrong_receipt = [False]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append((self.path, request))
                if self.path == '/identity':
                    response = {'authorization': 'independent-aimee-binding'}
                elif request.get('authorization') != 'independent-aimee-binding':
                    self.send_response(403)
                    self.send_header('Content-Length', '2')
                    self.end_headers()
                    self.wfile.write(b'{}')
                    return
                elif self.path == '/search':
                    response = dict(status='ok', facts=[dict(id='5', content='Remote fixture result')], windows=[])
                else:
                    response = dict(authorization='wrong-binding' if wrong_receipt[0] else 'independent-aimee-binding',
                                    view='independent-remote-view', refs=[dict(namespace='remote-fixture', id='5', revision='v1')])
                raw = json.dumps(response).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        server = socketserver.UnixStreamServer(str(self.root/'nonexistent-gateway.sock'), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        def close():
            server.shutdown()
            server.server_close()
            worker.join()
        self.addCleanup(close)
        for generation in range(2):
            if generation:
                image2 = self.publish('two', 'amber')
                link = self.root/'next'
                link.symlink_to(image2, target_is_directory=True)
                link.replace(self.active)
            before = len(calls)
            self.call('begin')
            self.assertIn('facts', self.read()['result'])
            self.assertEqual(len(calls), before, 'local read contacted the gateway')
            for _ in range(2):
                r = self.call('native_search', query='remote fixture query', limit=4)['result']
                self.assertEqual(r['facts'][0]['memory_ref']['namespace'], 'remote-fixture')
            self.assertEqual([route for route, _ in calls[before:]], ['/identity','/search','/resolve','/search','/resolve'])
        wrong_receipt[0] = True
        r = self.call('native_search', query='remote fixture query', limit=4)['result']
        self.assertTrue(r['denied'], 'mismatched remote result accepted')


if __name__ == '__main__':
    unittest.main()
