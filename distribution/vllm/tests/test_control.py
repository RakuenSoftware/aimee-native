import asyncio
from types import SimpleNamespace as NS
import unittest
from aimee_vllm.control import operate
class ControlTests(unittest.IsolatedAsyncioTestCase):
    def owner(self):
        idle=asyncio.Event();idle.set()
        return NS(paused=False,poisoned=False,active=0,idle=idle,config={'serve':{'tensor_parallel_size':2}},banks={'old':1},pending_digest='new',load_banks=lambda:{'new':2})
    async def test_refresh_stays_closed_until_every_worker_acknowledges_same_revision(self):
        o=self.owner();calls=[]
        async def rpc(*args,**kw):
            self.assertTrue(o.paused);calls.append(1)
            return [{'publications':1,'pinned_requests':0,'catalog_digest':'new'}]*2
        result=await operate(o,NS(collective_rpc=rpc),{'op':'refresh'})
        self.assertEqual(result['workers'],2);self.assertFalse(o.paused);self.assertEqual(o.banks,{'new':2})
    async def test_mixed_revision_never_reopens_admission(self):
        o=self.owner()
        async def rpc(*args,**kw):return [{'publications':1,'pinned_requests':0,'catalog_digest':d} for d in ['new','old']]
        with self.assertRaises(RuntimeError):await operate(o,NS(collective_rpc=rpc),{'op':'refresh'})
        self.assertTrue(o.paused and o.poisoned);self.assertEqual(o.banks,{'old':1})
    async def test_withdraw_stops_new_admissions(self):
        o=self.owner();o.active=2
        result=await operate(o,None,{'op':'withdraw'})
        self.assertTrue(o.paused);self.assertEqual(result['active_requests'],2)

    async def test_poisoned_status_requests_supervised_restart(self):
        o=self.owner();o.poisoned=True
        self.assertEqual((await operate(o,None,{'op':'status'}))['state'],'restart_required')

    async def test_superseded_activation_cannot_reopen_after_withdrawal(self):
        o=self.owner()
        first=await operate(o,None,{'op':'withdraw'})
        second=await operate(o,None,{'op':'withdraw'})
        self.assertGreater(second['generation'],first['generation'])
        with self.assertRaisesRegex(RuntimeError,'superseded'):
            await operate(o,None,{'op':'refresh','generation':first['generation']})
        self.assertTrue(o.paused);self.assertFalse(o.poisoned)
        async def rpc(*args,**kw):return [{'publications':1,'pinned_requests':0,'catalog_digest':'new'}]*2
        await operate(o,NS(collective_rpc=rpc),{'op':'refresh','generation':second['generation']})
        self.assertFalse(o.paused)

    async def test_metrics_require_every_rank_and_do_not_change_admission(self):
        o=self.owner()
        async def partial(*args,**kw):return [{}]
        with self.assertRaisesRegex(RuntimeError,'incomplete worker metrics'):
            await operate(o,NS(collective_rpc=partial),{'op':'metrics'})
        self.assertFalse(o.paused);self.assertFalse(o.poisoned)
        async def complete(name,**kw):
            self.assertEqual(name,'aimee_cache_stats');return [{'rank':0},{'rank':1}]
        result=await operate(o,NS(collective_rpc=complete),{'op':'metrics'})
        self.assertEqual(len(result['workers']),2);self.assertFalse(o.paused)

    async def test_drain_timeout_is_retryable_without_worker_poisoning(self):
        o=self.owner();o.active=1;o.idle.clear();o.config['refresh_drain_timeout_seconds']=.01
        calls=[]
        async def rpc(*args,**kwargs):
            calls.append(1);return [{'publications':1,'pinned_requests':0,'catalog_digest':'new'}]*2
        engine=NS(collective_rpc=rpc)
        with self.assertRaises(TimeoutError):await operate(o,engine,{'op':'refresh'})
        self.assertTrue(o.paused);self.assertFalse(o.poisoned)
        self.assertEqual(calls,[]);self.assertEqual(o.banks,{'old':1})
        o.active=0;o.idle.set()
        self.assertEqual((await operate(o,engine,{'op':'refresh'}))['state'],'active')
        self.assertEqual(len(calls),1)

    async def test_cancelled_drain_does_not_poison_untouched_workers(self):
        o=self.owner();o.idle.clear()
        task=asyncio.create_task(operate(o,None,{'op':'refresh'}))
        await asyncio.sleep(0);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(o.paused);self.assertFalse(o.poisoned)

    async def test_invalid_local_catalog_is_retryable_without_worker_mutation(self):
        o=self.owner()
        def bad():raise ValueError('invalid catalog')
        o.load_banks=bad
        with self.assertRaises(ValueError):await operate(o,None,{'op':'refresh'})
        self.assertTrue(o.paused);self.assertFalse(o.poisoned);self.assertEqual(o.banks,{'old':1})
