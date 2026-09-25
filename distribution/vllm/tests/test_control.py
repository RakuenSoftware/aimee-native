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
