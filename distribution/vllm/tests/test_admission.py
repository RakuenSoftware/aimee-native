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
        m.config={};m.catalog_digest='fixture';m.paused=False;m.active=0;m.idle=asyncio.Event();m.idle.set()
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

    async def test_gemma_lifespan_exception_restores_owned_renderer(self):
        from types import SimpleNamespace as NS
        from unittest.mock import patch
        async def original(request):return None
        handler=NS(render_chat_request=original)
        application=NS(state=NS(openai_serving_chat=handler,engine_client=None))
        async def app(scope,receive,send):
            await send({'type':'lifespan.startup.complete'})
            self.assertIsNot(handler.render_chat_request,original)
            raise RuntimeError('synthetic lifespan failure')
        owner=self.middleware(app)
        owner.model_adapter=NS(description={'prefix_renderer':'stock'})
        owner.gemma_contexts={}
        async def start(*args):return None
        async def receive():return None
        async def send(event):pass
        with patch('aimee_vllm.composition.metadata.version',return_value='0.30.0'), \
             patch('aimee_vllm.control.start',start):
            with self.assertRaisesRegex(RuntimeError,'synthetic lifespan'):
                await owner({'type':'lifespan','app':application},receive,send)
        self.assertIs(handler.render_chat_request,original)
        self.assertFalse(hasattr(handler,'_aimee_composition_owner'))

    async def test_gemma_verified_prefix_reaches_renderer_and_bad_requests_release_capacity(self):
        from pathlib import Path
        import tempfile
        from types import SimpleNamespace as NS
        from unittest.mock import patch
        from test_composition import StockTokenizer
        from aimee_vllm.composition import prepare_contract, install_renderer, uninstall_renderer
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('tokenizer.json','tokenizer_config.json'):(root/name).write_text('{}')
            tokenizer=StockTokenizer()
            _,bank,contract=prepare_contract(tokenizer,root,'Approved instructions',['Fact.'], stock_render=tokenizer.render)
            seen=[]
            broken={'value':False}
            async def render(request):
                text=tokenizer.apply_chat_template(request.messages,add_generation_prompt=True)
                return request.messages,[{'type':'token','prompt_token_ids':[99] if broken['value'] else tokenizer.encode(text)}]
            handler=NS(render_chat_request=render,create_error_response=lambda message:{'error':message})
            async def app(scope,receive,send):
                body=json.loads((await receive())['body'])
                result=await handler.render_chat_request(NS(messages=body['messages'],vllm_xargs=body.get('vllm_xargs')))
                seen.append((body,result))
                await send({'type':'http.response.start','status':400 if isinstance(result,dict) else 200,'headers':[]})
                await send({'type':'http.response.body','body':b'done'})
            owner=self.middleware(app);owner.gemma_contexts={'a':contract}
            with patch('aimee_vllm.composition.metadata.version',return_value='0.30.0'):
                install_renderer(owner,NS(state=NS(openai_serving_chat=handler)))
            self.addCleanup(uninstall_renderer,owner)
            async def invoke(messages,**fields):
                events=[]
                async def receive():return {'type':'http.request','body':json.dumps(dict(fields,messages=messages,vllm_xargs={'aimee_publication':'a'})).encode()}
                async def send(event):events.append(event)
                await owner({'type':'http','method':'POST','path':'/v1/chat/completions'},receive,send)
                return events[0]['status']
            wrong=[{'role':'system','content':'Wrong instructions'},{'role':'user','content':'question'}]
            self.assertEqual(await invoke(wrong),400)
            self.assertEqual(seen,[])
            self.assertTrue(owner.ledger.acquire(2,10));owner.ledger.release(2)
            messages=[{'role':'system','content':'Approved instructions'},{'role':'user','content':'question with <bos> literal'}]
            self.assertEqual(await invoke(messages),200)
            self.assertEqual(seen[-1][0]['messages'],messages)
            expected=tokenizer.encode(tokenizer.apply_chat_template([{'role':'system','content':'Approved instructions\n\nAuthoritative memory:\nFact.'}]+messages[1:],add_generation_prompt=True))
            self.assertEqual(bank+seen[-1][1][1][0]['prompt_token_ids'],expected)
            self.assertTrue(owner.ledger.acquire(2,10));owner.ledger.release(2)
            broken['value']=True
            self.assertEqual(await invoke(messages),400)
            self.assertTrue(owner.ledger.acquire(2,10));owner.ledger.release(2)
            self.assertFalse(owner.poisoned)

    async def test_hybrid_context_is_verified_before_reservation_and_stripped_once(self):
        import hashlib
        received=[]
        async def app(scope,receive,send):
            received.append(json.loads((await receive())['body']))
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        m=self.middleware(app);m.hybrid_contexts={'a':hashlib.sha256(b'Approved instructions').hexdigest()}
        async def invoke(messages):
            events=[]
            async def receive():return {'type':'http.request','body':json.dumps({'messages':messages,'vllm_xargs':{'aimee_publication':'a'}}).encode()}
            async def send(event):events.append(event)
            await m({'type':'http','method':'POST','path':'/v1/chat/completions'},receive,send)
            return events
        for messages in ([{'role':'system','content':'Wrong instructions'},{'role':'user','content':'question'}],
                         ['invalid'],[{'role':'system','content':['invalid']}],
                         [{'role':'system','content':'Approved instructions'}]):
            self.assertEqual((await invoke(messages))[0]['status'],400)
            self.assertTrue(m.ledger.acquire(2,10));m.ledger.release(2)
        messages=[{'role':'system','content':'  Approved instructions\n'},{'role':'user','content':'question'}]
        self.assertEqual((await invoke(messages))[0]['status'],200)
        self.assertEqual(received[0]['messages'],messages[1:])
        self.assertEqual(messages[0]['role'],'system')

    async def test_hybrid_catalogue_does_not_strip_system_context_from_empty_selection(self):
        import hashlib
        from unittest.mock import patch
        received=[]
        async def app(scope,receive,send):
            received.append(json.loads((await receive())['body']))
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        m=self.middleware(app);m.config={'selection_socket':'fixture'}
        m.hybrid_contexts={'a':hashlib.sha256(b'Approved instructions').hexdigest()}
        messages=[{'role':'system','content':'Other ordinary instructions'},{'role':'user','content':'question'}]
        async def select(*args):return {'publication':None,'catalog_digest':'fixture'}
        async def receive():return {'type':'http.request','body':json.dumps({'messages':messages}).encode()}
        events=[]
        async def send(event):events.append(event)
        with patch('aimee_vllm.selection.select',select):
            await m({'type':'http','method':'POST','path':'/v1/chat/completions'},receive,send)
        self.assertEqual(events[0]['status'],200)
        self.assertEqual(received[0]['messages'],messages)
    async def test_unknown_rejected_and_interrupted_request_retains_reservation(self):
        async def fail(scope,receive,send):raise asyncio.CancelledError()
        m=self.middleware(fail)
        self.assertEqual((await self.call(m,'unknown'))[0]['status'],400)
        with self.assertRaises(asyncio.CancelledError):await self.call(m,'a')
        self.assertTrue(m.poisoned)
        self.assertEqual((await self.call(m,'b'))[0]['status'],503)

    async def test_automatic_selection_overrides_caller_publication(self):
        from unittest.mock import patch
        received=[]
        async def app(scope,receive,send):
            received.append(json.loads((await receive())['body']))
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        m=self.middleware(app);m.config={'selection_socket':'fixture'}
        async def select(*args):return {'publication':'a','catalog_digest':'fixture'}
        with patch('aimee_vllm.selection.select',select):
            result=await self.call(m,'untrusted-publication')
        self.assertEqual(result[0]['status'],200)
        self.assertEqual(received[0]['vllm_xargs']['aimee_publication'],'a')

    async def test_authorized_empty_overrides_caller_without_reserving_bank(self):
        from unittest.mock import patch
        received=[]
        async def app(scope,receive,send):
            received.append(json.loads((await receive())['body']))
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        m=self.middleware(app);m.config={'selection_socket':'fixture'}
        async def select(*args):return {'publication':None,'catalog_digest':'fixture'}
        with patch('aimee_vllm.selection.select',select):
            result=await self.call(m,'a')
        self.assertEqual(result[0]['status'],200)
        self.assertNotIn('aimee_publication',received[0]['vllm_xargs'])
        self.assertEqual(received[0]['vllm_xargs']['aimee_catalog_digest'],'fixture')
        from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest
        ChatCompletionRequest(model='fixture',messages=[{'role':'user','content':'17+24'}],vllm_xargs=received[0]['vllm_xargs'])
        self.assertTrue(m.ledger.acquire(2,10));m.ledger.release(2)

    async def test_selection_error_is_not_empty_success(self):
        from unittest.mock import patch
        async def app(*args):self.fail('generation received failed authorization')
        m=self.middleware(app);m.config={'selection_socket':'fixture'}
        async def select(*args):raise RuntimeError('unavailable')
        with patch('aimee_vllm.selection.select',select):
            self.assertEqual((await self.call(m,'a'))[0]['status'],503)

    async def test_selection_revision_race_rejects_before_generation(self):
        from unittest.mock import patch
        async def app(*args):self.fail('generation received a stale selection')
        m=self.middleware(app);m.config={'selection_socket':'fixture'}
        async def select(*args):return {'publication':'a','catalog_digest':'stale'}
        with patch('aimee_vllm.selection.select',select):
            result=await self.call(m,'a')
        self.assertEqual(result[0]['status'],503)

    async def test_paused_selection_can_activate_but_cannot_bypass_pause(self):
        from unittest.mock import patch
        reached=[]
        async def app(scope,receive,send):
            reached.append(True)
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        m=self.middleware(app);m.config={'selection_socket':'fixture'};m.paused=True
        async def unchanged(*args):return {'publication':'a','catalog_digest':'fixture'}
        with patch('aimee_vllm.selection.select',unchanged):
            self.assertEqual((await self.call(m,'a'))[0]['status'],503)
        self.assertFalse(reached)
        async def activated(*args):
            m.paused=False
            return {'publication':'a','catalog_digest':'fixture'}
        with patch('aimee_vllm.selection.select',activated):
            self.assertEqual((await self.call(m,'a'))[0]['status'],200)
        self.assertTrue(reached)

    async def test_done_disconnect_releases_but_interrupted_stream_stays_pinned(self):
        for completed in (False,True):
            async def app(scope,receive,send):
                await receive()
                await send({'type':'http.response.start','status':200,'headers':[(b'content-type',b'text/event-stream')]})
                wire=b'data: {"choices":[{"index":0,"finish_reason":"stop"}]}\n\n' if completed else b'data: {"choices":[{"index":0,"finish_reason":null}]}\n\n'
                if completed:wire+=b'data: [DONE]\n\n'
                await send({'type':'http.response.body','body':wire,'more_body':True})
                self.assertEqual((await receive())['type'],'http.disconnect')
                raise asyncio.CancelledError()
            m=self.middleware(app)
            events=iter([{'type':'http.request','body':json.dumps({'stream':True,'vllm_xargs':{'aimee_publication':'a'}}).encode()},{'type':'http.disconnect'}])
            async def receive():return next(events)
            async def send(event):pass
            with self.assertRaises(asyncio.CancelledError):
                await m({'type':'http','method':'POST','path':'/v1/chat/completions'},receive,send)
            self.assertEqual(m.poisoned,not completed)
            self.assertEqual(m.ledger.acquire(2,10),completed)
