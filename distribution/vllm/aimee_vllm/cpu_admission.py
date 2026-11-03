"""CPU profile reuses native admission framing and publisher UID checks."""
import asyncio,json,os
from pathlib import Path
from .admission import NativeAdmission
from .telemetry import Stages
class CPULedger:
    def __init__(self,budget):self.budget=budget;self.refs={};self.sizes={}
    def acquire(self,uid,size):
        if uid not in self.refs and sum(self.sizes.values())+size>self.budget:return False
        self.refs[uid]=self.refs.get(uid,0)+1;self.sizes[uid]=size;return True
    def release(self,uid):
        self.refs[uid]-=1
        if not self.refs[uid]:del self.refs[uid];del self.sizes[uid]
class NativeCPUAdmission(NativeAdmission):
    def __init__(self,app,config=None):
        self.app=app;self.config=config or json.loads(Path(os.environ['AIMEE_VLLM_CPU_CONFIG']).read_text())
        if self.config.get('cpu_native_profile') is not True:raise ValueError('explicit CPU native profile required')
        if not self.config.get('research_owner_fixture') and not self.config.get('selection_socket'):raise ValueError('CPU serving requires enrolled owner selection or an explicit research fixture')
        self.poisoned=False;self.paused=True;self.active=0;self.idle=asyncio.Event();self.idle.set();self.generation=0
        self.ledger=CPULedger(self.config.get('host_memory_budget',512*1024**2));self.stages=Stages(False)
        self.banks={};self.pending_bank=None;self.catalog_digest='';self.pending_digest='';self.hybrid_contexts={};self.authentication=None
        if self.config.get('selection_socket'):
            from vllm.entrypoints.serve.middleware.authenticate import AuthenticationMiddleware
            key=os.environ.get('VLLM_API_KEY','')
            if not key.strip():raise ValueError('enrolled CPU serving requires VLLM_API_KEY')
            self.authentication=AuthenticationMiddleware(self._admit,tokens=[key])

    async def _admit(self,scope,receive,send):
        if scope.get('type')!='http' or scope.get('method')!='POST' or scope.get('path') not in ('/v1/chat/completions','/v1/completions'):
            return await super()._admit(scope,receive,send)
        chunks=[];size=0
        while True:
            event=await receive()
            if event['type']=='http.disconnect':return
            chunk=event.get('body',b'');size+=len(chunk)
            if size>262144:return await self.error(send,413,'CPU request exceeds bounded input profile')
            chunks.append(chunk)
            if not event.get('more_body',False):break
        try:
            body=json.loads(b''.join(chunks));extras=body.get('vllm_xargs') or {}
            if not isinstance(extras,dict):raise ValueError()
            if 'aimee_cpu_capture' in extras:return await self.error(send,403,'private CPU capture control is not an HTTP argument')
            extras.pop('aimee_catalog_digest',None)
            if extras:body['vllm_xargs']=extras
            else:body.pop('vllm_xargs',None)
            raw=json.dumps(body).encode()
        except (ValueError,TypeError,AttributeError):return await self.error(send,400,'invalid CPU request')
        sent=False
        async def replay():
            nonlocal sent
            if not sent:sent=True;return {'type':'http.request','body':raw,'more_body':False}
            return await receive()
        rewritten=dict(scope);rewritten['headers']=[(k,v) for k,v in scope.get('headers',[]) if k.lower()!=b'content-length']+[(b'content-length',str(len(raw)).encode())]
        return await super()._admit(rewritten,replay,send)
