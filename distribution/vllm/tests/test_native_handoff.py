import asyncio
import importlib.util
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'aimee_vllm' / 'native_handoff.py'
spec = importlib.util.spec_from_file_location('native_handoff', SOURCE)
h = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = h
spec.loader.exec_module(h)


class Runtime:
    def __init__(self):
        self.publications = []
        self.outputs = [('I need measured throughput.', 'stop'), ('52 is below 70.', 'stop')]
        self.withdrawn = False
        self.fail_cleanup = False
    async def publish(self, publication): self.publications.append(publication)
    async def generate(self, request, publication): return self.outputs.pop(0)
    async def withdraw(self):
        self.withdrawn = True
        if self.fail_cleanup: raise RuntimeError('worker release unknown')


class Owner:
    def __init__(self): self.received = []; self.closed = []
    async def open(self, request): return h.Publication('999', 'Need a link assessment.')
    async def contribute(self, contribution):
        self.received.append(contribution)
        if contribution.ordinal == 0:
            return h.OwnerReply(contribution.request, 0, contribution.publication_sha256,
                                'resume', h.Publication('001', 'Measured throughput:52MB/s.'))
        return h.OwnerReply(contribution.request, 1, contribution.publication_sha256,
                            'complete', output=contribution.text)
    async def close(self, request, reason): self.closed.append((request, reason))


class HandoffTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.runtime = Runtime(); self.owner = Owner()
        self.request = h.Request('actor', 'session', 'request', 'task')
        self.driver = h.NativeHandoff(self.runtime, self.owner)
    async def test_owner_can_distribute_lexically_older_revision(self):
        result = await self.driver.run(self.request)
        self.assertEqual(result.output, '52 is below 70.')
        self.assertEqual([p.revision for p in self.runtime.publications], ['999', '001'])
        self.assertEqual([p.ordinal for p in self.owner.received], [0, 1])
        self.assertTrue(self.runtime.withdrawn)
        self.assertEqual(self.owner.closed[-1][1], 'complete')
    async def test_nonterminal_text_never_reaches_owner(self):
        self.runtime.outputs = [('Execute a tool now', 'length')]
        with self.assertRaisesRegex(h.HandoffError, 'nonterminal'):
            await self.driver.run(self.request)
        self.assertFalse(self.owner.received)
        self.assertTrue(self.runtime.withdrawn)
    async def test_foreign_session_reply_is_rejected(self):
        original = self.owner.contribute
        async def foreign(c): return replace(await original(c), request=replace(c.request, session='foreign'))
        self.owner.contribute = foreign
        with self.assertRaisesRegex(h.HandoffError, 'binding'):
            await self.driver.run(self.request)
        self.assertEqual(len(self.runtime.publications), 1)
    async def test_stale_ordinal_and_digest_rejected(self):
        original = self.owner.contribute
        async def stale(c): return replace(await original(c), ordinal=7, publication_sha256='wrong')
        self.owner.contribute = stale
        with self.assertRaisesRegex(h.HandoffError, 'binding'):
            await self.driver.run(self.request)
    async def test_budget_exhaustion_returns_no_model_output(self):
        self.driver.max_rounds = 1
        with self.assertRaisesRegex(h.HandoffError, 'budget'):
            await self.driver.run(self.request)
        self.assertTrue(self.runtime.withdrawn)
    async def test_failed_cleanup_prevents_next_request(self):
        self.runtime.fail_cleanup = True
        with self.assertRaisesRegex(h.HandoffError, 'cleanup'):
            await self.driver.run(self.request)
        with self.assertRaisesRegex(h.HandoffError, 'restart'):
            await self.driver.run(self.request)
        self.assertEqual(self.owner.closed[-1][1], 'complete')
    async def test_cancel_during_generation_cleans_both_sides(self):
        started = asyncio.Event()
        async def wait(*args): started.set(); await asyncio.Event().wait()
        self.runtime.generate = wait
        task = asyncio.create_task(self.driver.run(self.request))
        await started.wait(); task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(self.runtime.withdrawn)
        self.assertEqual(self.owner.closed[-1][1], 'cancelled')
    async def test_request_deadline_cleans_both_sides(self):
        async def wait(*args): await asyncio.Event().wait()
        self.runtime.generate = wait; self.driver.timeout_seconds = .01
        with self.assertRaises(TimeoutError): await self.driver.run(self.request)
        self.assertTrue(self.runtime.withdrawn)
        self.assertTrue(self.owner.closed)
    async def test_parallel_requests_do_not_mix_publications(self):
        entered = asyncio.Event(); release = asyncio.Event(); events = []
        async def open_request(req):
            events.append(('open', req.request_id))
            return h.Publication(req.request_id, 'Native task '+req.request_id)
        async def generate(req, pub):
            self.assertEqual(req.request_id, pub.revision)
            events.append(('generate', req.request_id)); entered.set()
            if req.request_id == 'first': await release.wait()
            return 'proposed content', 'stop'
        async def contribute(c):
            return h.OwnerReply(c.request, c.ordinal, c.publication_sha256, 'complete')
        self.owner.open = open_request; self.owner.contribute = contribute
        self.runtime.generate = generate
        first = asyncio.create_task(self.driver.run(replace(self.request, request_id='first')))
        await entered.wait()
        second = asyncio.create_task(self.driver.run(replace(self.request, request_id='second')))
        await asyncio.sleep(0)
        self.assertNotIn(('open', 'second'), events)
        release.set(); await asyncio.gather(first, second)
        self.assertEqual(events, [('open','first'), ('generate','first'), ('open','second'), ('generate','second')])
    async def test_second_cancel_keeps_lane_poisoned(self):
        generating = asyncio.Event(); cleaning = asyncio.Event()
        async def generate(*args): generating.set(); await asyncio.Event().wait()
        async def withdraw(): cleaning.set(); await asyncio.Event().wait()
        self.runtime.generate = generate; self.runtime.withdraw = withdraw
        task = asyncio.create_task(self.driver.run(self.request))
        await generating.wait(); task.cancel(); await cleaning.wait(); task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        with self.assertRaisesRegex(h.HandoffError, 'restart'):
            await self.driver.run(self.request)
    async def test_real_unix_transport_preserves_request_and_revision(self):
        async def serve(reader, writer):
            message = json.loads(await reader.readline())
            if message['op'] == 'open':
                req = h.Request(**message['request'])
                response = dict(request=message['request'], publication=vars(await self.owner.open(req)))
            elif message['op'] == 'contribute':
                c = message['contribution']; c['request'] = h.Request(**c['request'])
                response = __import__('dataclasses').asdict(await self.owner.contribute(h.Contribution(**c)))
            else:
                await self.owner.close(h.Request(**message['request']), message['reason'])
                response = dict(closed=True, request=message['request'])
            writer.write(json.dumps(response).encode()+b'\n'); await writer.drain()
            writer.close(); await writer.wait_closed()
        with tempfile.TemporaryDirectory() as tmp:
            socket = str(Path(tmp)/'owner.sock')
            server = await asyncio.start_unix_server(serve, path=socket)
            async with server:
                result = await h.NativeHandoff(self.runtime, h.UnixOwner(socket)).run(self.request)
            self.assertEqual(result.output, '52 is below 70.')
            self.assertEqual(self.owner.closed[-1][1], 'complete')


if __name__ == '__main__': unittest.main()
