"""Publisher-controlled CPU preparation through actual private engine calls."""
import asyncio,hashlib,uuid
async def operate(owner,engine,request):
    op=request.get('op')
    if request=={'op':'metrics'}:
        return dict(workers=await engine.collective_rpc('aimee_cpu_metrics',timeout=30),active_requests=owner.active,state='restart_required' if owner.poisoned else ('paused' if owner.paused else 'active'))
    if request=={'op':'status'}:return dict(state='restart_required' if owner.poisoned else ('paused' if owner.paused else 'active'))
    if request=={'op':'withdraw'}:
        owner.paused=True;owner.generation+=1
        return dict(state='withdrawn',generation=owner.generation,active_requests=owner.active)
    if owner.poisoned:raise RuntimeError('CPU worker restart required')
    if type(request.get('generation')) is not int or request['generation']!=owner.generation:raise RuntimeError('CPU publisher generation mismatch')
    if not owner.paused:raise RuntimeError('CPU publisher must withdraw before preparation')
    generation=owner.generation
    await asyncio.wait_for(owner.idle.wait(),owner.config.get('refresh_drain_timeout_seconds',60))
    if generation!=owner.generation:raise RuntimeError('superseded CPU publication')
    if op=='prepare':
        if set(request)!={'op','generation','publication','revision'} or not isinstance(request['publication'],str) or not request['publication'] or len(request['publication'].encode())>65536 or not isinstance(request['revision'],str) or not request['revision'] or len(request['revision'])>128:raise ValueError('invalid CPU publication')
        def tokenize():
            from transformers import AutoTokenizer
            tok=AutoTokenizer.from_pretrained(owner.config['model'],local_files_only=True)
            text=tok.apply_chat_template([{'role':'system','content':'Authoritative memory:\n'+request['publication']}],tokenize=False,add_generation_prompt=False,enable_thinking=False)
            return tok.encode(text,add_special_tokens=False)
        tokens=await asyncio.to_thread(tokenize)
        if not 0<len(tokens)<=min(1024,owner.config.get('max_model_len',4096)-512):raise ValueError('CPU prefix budget exceeded')
        rid='aimee-cpu-prepare-'+uuid.uuid4().hex;nonce=uuid.uuid4().hex;digest=hashlib.sha256(request['publication'].encode()).hexdigest()
        await engine.collective_rpc('aimee_cpu_quiesce',timeout=30)
        await engine.collective_rpc('aimee_cpu_arm_capture',args=(rid,nonce,len(tokens),request['revision'],digest),timeout=30)
        try:
            from vllm import SamplingParams
            async for _ in engine.generate({'prompt_token_ids':tokens},SamplingParams(temperature=0,max_tokens=1,extra_args={'aimee_cpu_capture':nonce}),rid):pass
            banks=await engine.collective_rpc('aimee_cpu_finish_capture',timeout=60)
        except BaseException:
            owner.poisoned=True
            await engine.abort(rid)
            raise
        if len(banks)!=1 or generation!=owner.generation:raise RuntimeError('superseded/incomplete CPU capture')
        owner.pending_bank=banks[0];owner.pending_digest=banks[0]['fingerprint']
        return dict(state='prepared',publication=banks[0])
    if op=='refresh' and set(request)=={'op','generation'}:
        bank=owner.pending_bank
        if bank is None:raise RuntimeError('no prepared CPU publication')
        metrics=await engine.collective_rpc('aimee_cpu_metrics',timeout=30)
        if len(metrics)!=1 or metrics[0]['pinned_requests']!=0 or metrics[0]['publications']!=1 or metrics[0]['bank_fingerprints']!={bank['revision']:bank['fingerprint']}:raise RuntimeError('CPU worker not quiescent/prepared')
        if generation!=owner.generation:raise RuntimeError('superseded CPU activation')
        owner.banks={bank['revision']:(0,bank['bytes'])};owner.catalog_digest=owner.pending_digest;owner.paused=False
        return dict(state='active',publications=1,workers=1)
    raise ValueError('unsupported CPU control operation')
