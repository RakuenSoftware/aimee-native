"""Admission-level cache isolation without a GPU or private Rust library."""
import asyncio
import importlib
import json
import sys
from types import ModuleType
import unittest
from unittest.mock import patch


class FakeLedger:
    def __init__(self): self.active=set()
    def acquire(self,uid,size): self.active.add(uid);return True
    def release(self,uid): self.active.remove(uid)


class AdmissionCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_publication_refresh_drains_active_request_and_changes_cache_namespace(self):
        store=ModuleType('aimee_vllm.store');store.PreparedStore=object
        with patch.dict(sys.modules,{'aimee_vllm.store':store}):
            admission=importlib.import_module('aimee_vllm.admission')
            control=importlib.import_module('aimee_vllm.control')
        entered=asyncio.Event();release=asyncio.Event();observed=[]
        async def app(scope,receive,send):
            body=json.loads((await receive())['body']);observed.append(body)
            if len(observed)==1:
                entered.set();await release.wait()
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        m=admission.NativeAdmission.__new__(admission.NativeAdmission)
        m.app=app;m.poisoned=False;m.paused=False;m.active=0;m.idle=asyncio.Event();m.idle.set()
        m.config={'recipient':'recipient-1','selection_socket':'test',
                  'serve':{'enable_prefix_caching':True,'tensor_parallel_size':1}}
        m.catalog_digest='revision-1';m.banks={'bank-a':(1,10)};m.ledger=FakeLedger()
        def replacement():
            m.pending_digest='revision-2'
            return {'bank-a':(2,10)}
        m.load_banks=replacement
        class Engine:
            async def collective_rpc(self,name,timeout):
                return [{'publications':1,'pinned_requests':0,'catalog_digest':m.pending_digest}]
        async def select(path,body):return {'publication':'bank-a','catalog_digest':m.catalog_digest}
        async def call():
            data=json.dumps({'messages':[{'role':'user','content':'native'}]}).encode()
            events=[]
            async def receive():return {'type':'http.request','body':data,'more_body':False}
            async def send(event):events.append(event)
            await m({'type':'http','method':'POST','path':'/v1/chat/completions','headers':[]},receive,send)
            return events
        with patch('aimee_vllm.selection.select',select):
            first=asyncio.create_task(call());await entered.wait()
            refresh=asyncio.create_task(control.operate(m,Engine(),{'op':'refresh'}))
            await asyncio.sleep(0)
            self.assertTrue(m.paused)
            self.assertFalse(refresh.done())
            self.assertEqual((await call())[0]['status'],503)
            release.set();self.assertEqual((await first)[0]['status'],200)
            self.assertEqual((await refresh)['state'],'active')
            self.assertEqual((await call())[0]['status'],200)
        self.assertEqual(len(observed),2)
        self.assertNotEqual(observed[0]['cache_salt'],observed[1]['cache_salt'])
        self.assertEqual(observed[0]['vllm_xargs']['aimee_catalog_digest'],'revision-1')
        self.assertEqual(observed[1]['vllm_xargs']['aimee_catalog_digest'],'revision-2')

    async def test_concurrent_native_and_empty_requests_keep_authorized_cache_identities(self):
        store=ModuleType('aimee_vllm.store');store.PreparedStore=object
        with patch.dict(sys.modules,{'aimee_vllm.store':store}):
            admission=importlib.import_module('aimee_vllm.admission')
        observed=[];entered=asyncio.Event();release=asyncio.Event()
        async def app(scope,receive,send):
            body=json.loads((await receive())['body']);observed.append(body)
            if body['messages'][0]['content']=='native':
                entered.set();await release.wait()
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        m=admission.NativeAdmission.__new__(admission.NativeAdmission)
        m.app=app;m.poisoned=False;m.paused=False;m.active=0;m.idle=asyncio.Event();m.idle.set()
        m.config={'recipient':'recipient-1','selection_socket':'test','serve':{'enable_prefix_caching':True}}
        m.catalog_digest='revision-1';m.banks={'bank-a':(1,10)};m.ledger=FakeLedger()
        async def select(path,body):
            return {'publication':'bank-a' if body['messages'][0]['content']=='native' else None,
                    'catalog_digest':m.catalog_digest}
        async def call(question):
            data=json.dumps({'messages':[{'role':'user','content':question}],
                             'cache_salt':'caller-controlled',
                             'vllm_xargs':{'aimee_publication':'untrusted'}}).encode()
            events=[]
            async def receive():return {'type':'http.request','body':data,'more_body':False}
            async def send(event):events.append(event)
            await m({'type':'http','method':'POST','path':'/v1/chat/completions','headers':[]},receive,send)
            return events
        with patch('aimee_vllm.selection.select',select):
            first=asyncio.create_task(call('native'));await entered.wait()
            empty=await call('empty')
            self.assertEqual(empty[0]['status'],200)
            self.assertEqual(m.active,1)
            self.assertFalse(m.idle.is_set())
            release.set();self.assertEqual((await first)[0]['status'],200)
            self.assertTrue(m.idle.is_set())
        native,none=observed
        self.assertEqual(native['vllm_xargs']['aimee_publication'],'bank-a')
        self.assertNotIn('aimee_publication',none['vllm_xargs'])
        self.assertNotEqual(native['cache_salt'],none['cache_salt'])
        self.assertNotEqual(native['cache_salt'],'caller-controlled')
        self.assertEqual(native['cache_salt'],admission.cache_salt('recipient-1','revision-1','bank-a'))
        self.assertEqual(none['cache_salt'],admission.cache_salt('recipient-1','revision-1',None))
        self.assertEqual(m.ledger.active,set())


if __name__=='__main__': unittest.main()
