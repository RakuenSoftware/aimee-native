"""Supported ASGI middleware; Rust reserves native-bank capacity before vLLM.
One API process/recipient only. Publisher-controlled refresh drains requests.
"""
import asyncio
import hashlib
import ctypes
import json
import logging
import os
from pathlib import Path
from .store import PreparedStore
from .stream_completion import StreamCompletion
from .cache_identity import cache_salt

logger = logging.getLogger(__name__)

class Ledger:
    def __init__(self, lib, budget):
        self.lib=lib
        lib.aimee_admission_open.argtypes=[ctypes.c_size_t];lib.aimee_admission_open.restype=ctypes.c_void_p
        lib.aimee_admission_acquire.argtypes=[ctypes.c_void_p,ctypes.c_uint64,ctypes.c_size_t];lib.aimee_admission_acquire.restype=ctypes.c_bool
        lib.aimee_admission_release.argtypes=[ctypes.c_void_p,ctypes.c_uint64]
        lib.aimee_admission_close.argtypes=[ctypes.c_void_p]
        self.handle=lib.aimee_admission_open(budget)
    def acquire(self,uid,size):return self.lib.aimee_admission_acquire(self.handle,uid,size)
    def release(self,uid):self.lib.aimee_admission_release(self.handle,uid)
    def close(self):
        if self.handle:self.lib.aimee_admission_close(self.handle);self.handle=None
    def __del__(self):
        if getattr(self,'handle',None):self.close()

class NativeAdmission:
    def __init__(self, app, config=None):
        self.app=app;self.poisoned=False
        config=config or json.loads(Path(os.environ['AIMEE_VLLM_CONFIG']).read_text())
        self.config=config;self.paused=config.get("start_paused",False);self.active=0;self.idle=asyncio.Event();self.idle.set()
        self.ledger=Ledger(ctypes.CDLL(config["library"]),config.get("device_memory_budget",256*1024**2))
        self.banks=self.load_banks()
        self.catalog_digest=self.pending_digest

    def load_banks(self):
        config=self.config
        raw_catalog=Path(config["catalog"]).read_bytes()
        catalog=json.loads(raw_catalog)
        self.pending_digest=hashlib.sha256(raw_catalog).hexdigest()
        lib=ctypes.CDLL(config["library"])
        world=config.get("serve",{}).get("tensor_parallel_size",1)
        banks={}
        for uid,(name,spec) in enumerate(catalog['publications'].items()):
            store=PreparedStore(lib,{**spec,'byte_budget':config['host_memory_budget'],'disk_backed':config.get('disk_backed',False),'lossless_transport':False,'device_budget':config.get('device_memory_budget',256*1024**2)})
            try:banks[name]=(uid,max(store.prepare_plan(rank, world)[1]["bytes"] for rank in range(world)))
            finally:store.close()
        return banks

    async def error(self, send, status, message):
        body=json.dumps({'error':{'message':message,'type':'native_memory_admission'}}).encode()
        headers=[(b'content-type',b'application/json')]
        if status==429:headers.append((b'retry-after',b'1'))
        await send({'type':'http.response.start','status':status,'headers':headers})
        await send({'type':'http.response.body','body':body})

    async def __call__(self, scope, receive, send):
        if scope['type']=='lifespan':
            from .control import start
            server=None
            async def lifecycle(event):
                nonlocal server
                if event['type']=='lifespan.startup.complete':
                    server=await start(self,scope['app'].state.engine_client)
                if event['type']=='lifespan.shutdown.complete' and server is not None:
                    server.close();await server.wait_closed();Path(self.config['control_socket']).unlink(missing_ok=True)
                await send(event)
            return await self.app(scope,receive,lifecycle)
        if scope['type']!='http':return await self.app(scope,receive,send)
        if (self.poisoned or self.paused) and scope.get('path')=='/health':
            return await self.error(send,503,'native admission requires restart')
        if scope.get('method')!='POST':return await self.app(scope,receive,send)
        if scope.get('path') in ('/tokenize','/detokenize'):
            return await self.app(scope,receive,send)
        if scope.get('path') not in ('/v1/chat/completions','/v1/completions'):
            return await self.error(send,404,'endpoint is outside the certified native serving API')
        if self.poisoned or (self.paused and not self.config.get('selection_socket')):return await self.error(send,503,'native admission requires worker restart after interrupted request')
        chunks=[]
        while True:
            event=await receive()
            if event['type']=='http.disconnect':return
            chunks.append(event.get('body',b''))
            if not event.get('more_body',False):break
        if self.poisoned or (self.paused and not self.config.get('selection_socket')):return await self.error(send,503,'native publication update in progress')
        raw=b''.join(chunks)
        try:
            body=json.loads(raw)
            extras=body.get('vllm_xargs') or {}
            publication=extras.get('aimee_publication')
            if publication is not None and not isinstance(publication,str):raise ValueError()
        except (ValueError,AttributeError,TypeError):
            return await self.error(send,400,'invalid native request')
        selector=getattr(self,'config',{}).get('selection_socket')
        if selector:
            try:
                from .selection import select
                selected=await select(selector,body)
                if selected['catalog_digest']!=self.catalog_digest:
                    raise RuntimeError('selection/catalogue mismatch')
                publication=selected['publication']
                if publication is None:extras.pop('aimee_publication',None)
                else:extras['aimee_publication']=publication
                extras['aimee_catalog_digest']=self.catalog_digest
            except Exception as exc:
                logger.warning('native selection failed (%s): %s',type(exc).__name__,exc)
                return await self.error(send,503,'approved native memory is unavailable')
            if self.poisoned or self.paused:
                return await self.error(send,503,'native publication update in progress')
        bank=None
        if publication is not None:
            bank=self.banks.get(publication)
            if bank is None:return await self.error(send,400,'native publication unavailable')
            if not self.ledger.acquire(*bank):return await self.error(send,429,'native memory busy; retry after active requests finish')
            extras['aimee_catalog_digest']=self.catalog_digest
        if self.config.get('serve',{}).get('enable_prefix_caching',False):
            # vLLM hashes this salt into the first prefix block, so every
            # downstream text K/V block belongs to this authorized revision.
            # Never accept a caller's cache namespace for native execution.
            body['cache_salt']=cache_salt(self.config['recipient'],self.catalog_digest,publication)
        else:
            body.pop('cache_salt',None)
        if publication is not None or selector:
            body['vllm_xargs']=extras
        if publication is not None or selector or self.config.get('serve',{}).get('enable_prefix_caching',False):
            raw=json.dumps(body).encode()
            scope=dict(scope)
            scope['headers']=[(k,v) for k,v in scope.get('headers',[]) if k.lower()!=b'content-length']+[(b'content-length',str(len(raw)).encode())]
        self.active+=1;self.idle.clear()
        replayed=False;disconnected=False;complete=False
        stream=StreamCompletion(body.get("n",1));is_sse=False
        async def replay():
            nonlocal replayed,disconnected
            if not replayed:
                replayed=True;return {'type':'http.request','body':raw,'more_body':False}
            event=await receive()
            if event['type']=='http.disconnect':disconnected=True
            return event
        async def forward(event):
            nonlocal complete,is_sse
            if event['type']=='http.response.start':
                is_sse=(body.get('stream') is True and event['status']==200 and
                        any(k.lower()==b'content-type' and v.lower().startswith(b'text/event-stream')
                            for k,v in event.get('headers',[])))
            if is_sse and event['type']=='http.response.body':
                # Inspect engine output before delivery: a client may disconnect
                # as soon as it sees [DONE], before ASGI sends its final empty body.
                stream.feed(event.get('body',b''))
            await send(event)
            if event['type']=='http.response.body' and not event.get('more_body',False):complete=True
        try:
            await self.app(scope,replay,forward)
        finally:
            self.active-=1
            if self.active==0:self.idle.set()
            if bank is not None:
                if (complete and not disconnected) or (is_sse and stream.complete):self.ledger.release(bank[0])
                else:
                    # Do not assume an HTTP cancellation acknowledged GPU abort.
                    # Keep reservation and stop admission until a supervised restart.
                    self.poisoned=True
