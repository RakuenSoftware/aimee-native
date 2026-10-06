"""Exclusive private engine calls; source authority and selection stay in Rust."""
import asyncio
from pathlib import Path
import uuid


async def prepare(owner, engine, request, adapter):
    if owner.config.get('native_preparation_enabled') is not True:
        raise ValueError('enrolled preparation is disabled')
    if owner.poisoned or not owner.paused:
        raise RuntimeError('preparation requires withdrawn healthy admission')
    generation = getattr(owner, 'generation', 0)
    if type(request.get('generation')) is not int or request['generation'] != generation:
        raise RuntimeError('superseded preparation')
    if set(request) != {'op', 'generation', 'facts', 'context', 'destination'}:
        raise ValueError('invalid preparation fields')
    facts, context = request['facts'], request['context']
    if (not isinstance(facts, list) or not 1 <= len(facts) <= 32
            or any(not isinstance(fact, str) or not fact for fact in facts)
            or not isinstance(context, str)
            or len((''.join(facts) + context).encode()) > 1024 * 1024):
        raise ValueError('invalid source working set')
    root = Path(owner.config['preparation_root']).resolve(strict=True)
    destination = Path(request['destination'])
    if (not destination.is_absolute() or destination.parent.resolve(strict=True) != root
            or len(destination.name) != 64
            or any(c not in '0123456789abcdef' for c in destination.name)
            or destination.exists() or destination.is_symlink()):
        raise ValueError('preparation destination outside managed cache')
    await asyncio.wait_for(owner.idle.wait(), owner.config.get('refresh_drain_timeout_seconds', 600))
    if generation != getattr(owner, 'generation', 0):
        raise RuntimeError('superseded preparation')
    # The dedicated adapter chooses prefix rendering; encoding always uses
    # the installed model's stock tokenizer.
    def tokenize():
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(owner.config['model'], local_files_only=True)
        if adapter.description['prefix_renderer']=='adapter':
            text=adapter.call('render_prefix',context=context,facts=facts)['text']
        elif adapter.description['prefix_renderer']=='stock':
            from .composition import prepare_contract
            text, tokens, contract = prepare_contract(tokenizer, owner.config['model'],
                context, facts, owner.config.get('model_revision'))
            return {'text': text, 'composition': contract}, tokens
        else:
            raise ValueError('unsupported dedicated prefix renderer')
        return text, tokenizer.encode(text, add_special_tokens=False)
    text, tokens = await asyncio.to_thread(tokenize)
    if not tokens or len(tokens) > min(1024, owner.config['serve'].get('max_model_len', 2048) - 128):
        raise ValueError('selected source exceeds native prefix budget')
    argument = {'text': text, 'context': context}[adapter.description['capture_argument']]
    from vllm import SamplingParams
    request_id = 'aimee-prepare-' + uuid.uuid4().hex
    armed = False
    try:
        acknowledgments = await engine.collective_rpc(adapter.description['capture_rpc'],
            args=(tokens, argument, str(destination), True), timeout=60)
        armed = True
        if len(acknowledgments) != 1 or acknowledgments[0] != {'state': 'armed'}:
            raise RuntimeError('incomplete exclusive capture acknowledgement')
        async for _ in engine.generate({'prompt_token_ids': tokens},
                SamplingParams(temperature=0, max_tokens=1), request_id):
            pass
        publications = await engine.collective_rpc('aimee_capture_finish', timeout=120)
        armed = False
        if generation != getattr(owner, 'generation', 0) or len(publications) != 1:
            raise RuntimeError('superseded or incomplete preparation')
        return {'state': 'prepared', 'publication': publications[0]}
    except BaseException:
        # An interrupted worker capture is never silently reused or reopened.
        owner.poisoned = True
        try:
            await engine.abort(request_id)
        finally:
            if armed:
                try:
                    await engine.collective_rpc('aimee_capture_finish', timeout=30)
                except Exception:
                    pass
        raise
