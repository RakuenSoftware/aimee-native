import asyncio
import unittest
from types import SimpleNamespace
from aimee_vllm.cpu_control import operate
class CPUControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_poisoned_metrics_never_report_active(self):
        owner=SimpleNamespace(poisoned=True,paused=False,active=0)
        async def rpc(*args,**kwargs):return [{'pinned_requests':0}]
        result=await operate(owner,SimpleNamespace(collective_rpc=rpc),{'op':'metrics'})
        self.assertEqual(result['state'],'restart_required')
    async def test_stale_generation_cannot_prepare(self):
        owner=SimpleNamespace(poisoned=False,paused=True,generation=4)
        with self.assertRaisesRegex(RuntimeError,'generation mismatch'):
            await operate(owner,None,dict(op='prepare',generation=3,publication='old',revision='999'))
    async def test_withdraw_keeps_existing_request_count(self):
        owner=SimpleNamespace(poisoned=False,paused=False,generation=3,active=2)
        result=await operate(owner,None,{'op':'withdraw'})
        self.assertTrue(owner.paused)
        self.assertEqual(result,dict(state='withdrawn',generation=4,active_requests=2))
