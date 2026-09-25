import asyncio
import ctypes
import json
import os
import unittest
from aimee_vllm.admission import Ledger,NativeAdmission

@unittest.skipUnless(os.environ.get('AIMEE_STORE_LIBRARY'),'set Rust library')
class AdmissionTests(unittest.IsolatedAsyncioTestCase):
    def middleware(self,app):
        m=NativeAdmission.__new__(NativeAdmission);m.app=app;m.poisoned=False
        m.catalog_digest='fixture';m.paused=False;m.active=0;m.idle=asyncio.Event();m.idle.set()
        m.banks={'a':(1,10),'b':(2,10)}
        m.ledger=Ledger(ctypes.CDLL(os.environ['AIMEE_STORE_LIBRARY']),10)
        self.addCleanup(m.ledger.close);return m
    async def call(self,m,name):
        events=[]
        async def receive():return {'type':'http.request','body':json.dumps({'vllm_xargs':{'aimee_publication':name}}).encode()}
        async def send(event):events.append(event)
        await m({'type':'http','method':'POST','path':'/v1/chat/completions'},receive,send)
        return events
    async def test_pressure_rejected_before_app_and_capacity_released(self):
        started=asyncio.Event();finish=asyncio.Event();calls=[]
        async def app(scope,receive,send):
            calls.append(json.loads((await receive())['body']));started.set();await finish.wait()
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        m=self.middleware(app);first=asyncio.create_task(self.call(m,'a'));await started.wait()
        rejected=await self.call(m,'b');self.assertEqual(rejected[0]['status'],429);self.assertEqual(len(calls),1)
        finish.set();await first
        self.assertEqual((await self.call(m,'b'))[0]['status'],200)
    async def test_same_bank_shared_until_all_requests_finish(self):
        l=Ledger(ctypes.CDLL(os.environ['AIMEE_STORE_LIBRARY']),10);self.addCleanup(l.close)
        self.assertTrue(l.acquire(1,10));self.assertTrue(l.acquire(1,10));l.release(1)
        self.assertFalse(l.acquire(2,10));l.release(1);self.assertTrue(l.acquire(2,10))
    async def test_unknown_rejected_and_interrupted_request_retains_reservation(self):
        async def fail(scope,receive,send):raise asyncio.CancelledError()
        m=self.middleware(fail)
        self.assertEqual((await self.call(m,'unknown'))[0]['status'],400)
        with self.assertRaises(asyncio.CancelledError):await self.call(m,'a')
        self.assertTrue(m.poisoned)
        self.assertEqual((await self.call(m,'b'))[0]['status'],503)
