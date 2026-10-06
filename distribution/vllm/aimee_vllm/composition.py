"""Versioned Gemma transcript-prefix contract, applied after stock rendering."""
import hashlib
import json
from pathlib import Path
from importlib import metadata

FORMAT = 'gemma-context-bound-chat-prefix-v2'
LEGACY = 'legacy-independent-chat-v1'

def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()

def tokenizer_identity(root):
    root = Path(root)
    # Include the stock chat template and tokenizer configuration, not only vocabulary.
    identity = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in ('tokenizer.json', 'tokenizer_config.json', 'chat_template.jinja')
            if (root / name).is_file()}
    if 'tokenizer.json' not in identity or 'tokenizer_config.json' not in identity:
        raise ValueError('missing installed tokenizer identity files')
    return identity

def stock_request_renderer(handler):
    """Use the configured stock request renderer, including content conversion."""
    from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest
    def render(messages, generation=False):
        request = ChatCompletionRequest(model=handler.model_config.model,
            messages=messages, add_generation_prompt=generation,
            chat_template_kwargs={'enable_thinking': False})
        params = request.build_chat_params(handler.chat_template,
            handler.chat_template_content_format).with_defaults(handler.default_chat_template_kwargs)
        # Get both actual stock tokenization and the exact capture text. Reject
        # any renderer whose text cannot reproduce its request token sequence.
        _, token_prompt = handler.renderer.render_messages(messages, params)
        params.chat_template_kwargs['tokenize'] = False
        _, text_prompt = handler.renderer.render_messages(messages, params)
        text, tokens = text_prompt.get('prompt'), token_prompt.get('prompt_token_ids')
        if (not isinstance(text, str) or not isinstance(tokens, list)
                or set(token_prompt) != {'prompt_token_ids'}
                or handler.renderer.get_tokenizer().encode(text, add_special_tokens=False) != tokens):
            raise ValueError('stock Gemma preparation requires reproducible text-only rendering')
        return text, tokens
    return render

def prepare_contract(tokenizer, root, context, facts, revision=None, *, stock_render):
    def render(messages, generation=False):
        return stock_render(messages, generation)
    instruction = context.strip()
    system = {'role': 'system', 'content': instruction}
    memory = {'role': 'system', 'content': instruction + '\n\nAuthoritative memory:\n' + '\n'.join(facts)}
    text, bank = render([memory])
    _, request = render([system])
    task = {'role': 'user', 'content': 'Native prefix boundary verification.'}
    _, combined = render([memory, task], True)
    _, incoming = render([system, task], True)
    if (not request or combined[:len(bank)] != bank or incoming[:len(request)] != request
            or combined[len(bank):] != incoming[len(request):]):
        raise ValueError('stock chat template does not provide an exact native prefix boundary')
    contract = {'format': FORMAT, 'system_context_sha256': hashlib.sha256(instruction.encode()).hexdigest(),
                'request_prefix_tokens': request, 'request_prefix_sha256': digest(request),
                'bank_prefix_sha256': digest(bank), 'tokenizer_files': tokenizer_identity(root),
                'model_revision': revision}
    return text, bank, contract

def validate_contract(profile, config):
    contract = profile.get('composition')
    if contract is None:
        if config.get('gemma_composition') != LEGACY:
            raise ValueError('legacy Gemma memory requires explicit legacy-independent-chat-v1 opt-in')
        return None
    if not isinstance(contract, dict) or contract.get('format') != FORMAT:
        raise ValueError('unsupported Gemma composition profile')
    tokens = contract.get('request_prefix_tokens')
    if (not isinstance(tokens, list) or not 0 < len(tokens) <= 1024
            or any(type(t) is not int or t < 0 for t in tokens)
            or digest(tokens) != contract.get('request_prefix_sha256')):
        raise ValueError('invalid prepared request prefix')
    if (contract.get('tokenizer_files') != tokenizer_identity(config['model'])
            or contract.get('model_revision') != config.get('model_revision')):
        raise ValueError('prepared Gemma tokenizer/revision mismatch')
    context = config.get('native_system_context', '').strip()
    if hashlib.sha256(context.encode()).hexdigest() != contract.get('system_context_sha256'):
        raise ValueError('prepared Gemma instruction mismatch')
    return contract

def check_request(body, contract):
    if body.get('chat_template') is not None:
        raise ValueError('context-bound Gemma requires the installed stock chat template')
    messages = body.get('messages')
    if (not isinstance(messages, list) or len(messages) < 2
            or not isinstance(messages[0], dict) or messages[0].get('role') != 'system'
            or not isinstance(messages[0].get('content'), str)
            or hashlib.sha256(messages[0]['content'].strip().encode()).hexdigest() != contract['system_context_sha256']):
        raise ValueError('native system instruction context was not prepared')

def remaining_input(engine_input, contract):
    allowed = {'type', 'prompt_token_ids', 'prompt', 'cache_salt',
               'prompt_token_offsets', 'assistant_tokens_mask'}
    if (not isinstance(engine_input, dict) or engine_input.get('type') != 'token'
            or set(engine_input) - allowed
            or engine_input.get('prompt_token_offsets') is not None
            or engine_input.get('assistant_tokens_mask') is not None
            or not isinstance(engine_input.get('prompt_token_ids'), list)):
        raise ValueError('unsupported Gemma engine prompt layout')
    tokens = engine_input['prompt_token_ids']
    prefix = contract['request_prefix_tokens']
    if len(tokens) <= len(prefix) or tokens[:len(prefix)] != prefix:
        raise ValueError('stock rendered request does not match its prepared system prefix')
    # Keep every task token, role delimiter and generation marker untouched.
    result = dict(engine_input, prompt_token_ids=tokens[len(prefix):])
    for field in ('prompt', 'prompt_token_offsets', 'assistant_tokens_mask'):
        result.pop(field, None)
    return result

def install_renderer(owner, app):
    if metadata.version('vllm') != '0.30.0':
        raise RuntimeError('context-bound Gemma requires the validated vLLM 0.30.0 renderer')
    handler = app.state.openai_serving_chat
    if handler is None:
        raise RuntimeError('context-bound Gemma requires the stock chat renderer')
    if getattr(handler, '_aimee_composition_owner', None) is owner:
        return
    if getattr(handler, '_aimee_composition_owner', None) is not None:
        raise RuntimeError('chat renderer already belongs to another native admission')
    original = handler.render_chat_request
    async def render(request):
        result = await original(request)
        extras = request.vllm_xargs or {}
        publication = extras.get('aimee_publication')
        contract = owner.gemma_contexts.get(publication)
        if contract is None:
            return result
        if extras.get('aimee_catalog_digest') != owner.catalog_digest:
            return handler.create_error_response('superseded Gemma prefix admission')
        if not isinstance(result, tuple) or len(result) != 2:
            return result  # Preserve the stock renderer's ErrorResponse.
        conversation, inputs = result
        if len(inputs) != 1:
            return handler.create_error_response('context-bound Gemma requires one text prompt')
        try:
            adjusted = remaining_input(inputs[0], contract)
        except ValueError as exc:
            return handler.create_error_response(str(exc))
        return conversation, [adjusted]
    handler.render_chat_request = render
    handler._aimee_composition_owner = owner
    owner.composition_renderer = (handler, original, render)


def validate_publication(profile_bytes, index, spec):
    # Rust hashes exactly the profile.json bytes it writes; do not reserialize
    # across languages (serde builds can preserve insertion order).
    profile = json.loads(profile_bytes)
    model = hashlib.sha256(b'dedicated-model-prefix-v1\0' + profile_bytes).hexdigest()
    if model != spec['model'] or index['model'] != model:
        raise ValueError('Gemma composition/publication identity mismatch')
    tokens = index['records'][spec['key']]['tokens']
    key = hashlib.sha256(model.encode() + json.dumps(tokens, separators=(',', ':')).encode()).hexdigest()
    if key != spec['key'] or digest(tokens) != profile['composition']['bank_prefix_sha256']:
        raise ValueError('Gemma bank prefix identity mismatch')


def uninstall_renderer(owner):
    installed = getattr(owner, 'composition_renderer', None)
    if installed is None:
        return
    handler, original, wrapped = installed
    if handler.render_chat_request is wrapped:
        handler.render_chat_request = original
    if getattr(handler, '_aimee_composition_owner', None) is owner:
        del handler._aimee_composition_owner
    del owner.composition_renderer
