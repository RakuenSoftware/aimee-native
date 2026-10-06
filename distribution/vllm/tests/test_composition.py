import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import patch
from aimee_vllm.composition import (FORMAT, LEGACY, prepare_contract, validate_contract,
    check_request, remaining_input, install_renderer, uninstall_renderer, validate_publication)


class StockTokenizer:
    """Stock-shaped deterministic tokenizer with an unconditional BOS."""
    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False, **kwargs):
        text = '<bos>' + ''.join('<turn>' + m['role'] + '\n' + m['content'].strip() + '</turn>\n'
                                for m in messages)
        if add_generation_prompt:
            text += '<turn>assistant\n<thought></thought>'
        return text
    def encode(self, text, **kwargs):
        return list(text.encode())


class CompositionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ('tokenizer.json', 'tokenizer_config.json', 'chat_template.jinja'):
            (self.root / name).write_text('{}')
        self.tokenizer = StockTokenizer()
        self.config = {'model': str(self.root), 'model_revision': 'revision-1',
                       'native_system_context': 'Use memory.'}
        self.text, self.bank, self.contract = prepare_contract(self.tokenizer, self.root,
            'Use memory.', ['Canonical fact with literal <bos> markers.'], 'revision-1')

    def engine_input(self, messages):
        text = self.tokenizer.apply_chat_template(messages, add_generation_prompt=True)
        return {'type':'token', 'prompt_token_ids': self.tokenizer.encode(text), 'prompt': text, 'cache_salt': 'revision'}

    def test_exact_stock_boundary_retains_every_task_role_and_literal_marker(self):
        messages = [{'role': 'system', 'content': ' Use memory. '},
                    {'role': 'user', 'content': 'Question with <bos> and </turn> literal markers.'},
                    {'role': 'assistant', 'content': 'Prior answer.'},
                    {'role': 'user', 'content': 'Follow-up question?'}]
        check_request({'messages': messages}, self.contract)
        incoming = self.engine_input(messages)
        adjusted = remaining_input(incoming, self.contract)
        memory = {'role': 'system', 'content': 'Use memory.\n\nAuthoritative memory:\nCanonical fact with literal <bos> markers.'}
        control = self.engine_input([memory] + messages[1:])
        self.assertEqual(self.bank + adjusted['prompt_token_ids'], control['prompt_token_ids'])
        self.assertEqual(adjusted['cache_salt'], 'revision')
        self.assertIn('prompt', incoming)
        self.assertNotIn('prompt', adjusted)

    def test_mismatched_system_missing_task_and_custom_template_are_denied(self):
        for messages in ([], [{'role': 'user', 'content': 'Use memory.'}],
                         [{'role': 'system', 'content': 'Wrong.'}, {'role': 'user', 'content': 'Q'}],
                         [{'role': 'system', 'content': 'Use memory.'}]):
            with self.assertRaises(ValueError): check_request({'messages': messages}, self.contract)
        with self.assertRaises(ValueError):
            check_request({'messages': [{'role': 'system', 'content': 'Use memory.'},
                          {'role': 'user', 'content': 'Q'}], 'chat_template': 'custom'}, self.contract)
        for incoming in ({'prompt_token_ids': self.bank + [99]},
                         {'prompt_token_ids': self.contract['request_prefix_tokens']},
                         {'prompt_token_ids': [99] + self.contract['request_prefix_tokens']},
                         {'encoder_prompt': {}}):
            with self.assertRaises(ValueError): remaining_input(incoming, self.contract)

    def test_empty_context_uses_explicit_stock_system_prefix(self):
        _, bank, contract = prepare_contract(self.tokenizer, self.root, '', ['Fact.'])
        messages = [{'role': 'system', 'content': ''}, {'role': 'user', 'content': 'Q?'}]
        check_request({'messages': messages}, contract)
        adjusted = remaining_input(self.engine_input(messages), contract)
        control = self.engine_input([{'role': 'system', 'content': '\n\nAuthoritative memory:\nFact.'}, messages[1]])
        self.assertEqual(bank + adjusted['prompt_token_ids'], control['prompt_token_ids'])

    def test_legacy_requires_explicit_opt_in_and_new_profiles_fail_on_identity_changes(self):
        with self.assertRaisesRegex(ValueError, 'legacy'): validate_contract({}, self.config)
        self.assertIsNone(validate_contract({}, dict(self.config, gemma_composition=LEGACY)))
        profile = {'composition': self.contract}
        self.assertEqual(validate_contract(profile, self.config), self.contract)
        for field, value in [('model_revision', 'revision-2'), ('native_system_context', 'Wrong')]:
            with self.assertRaises(ValueError): validate_contract(profile, dict(self.config, **{field: value}))
        corrupt = copy.deepcopy(profile)
        corrupt['composition']['request_prefix_tokens'][0] += 1
        with self.assertRaises(ValueError): validate_contract(corrupt, self.config)
        (self.root / 'chat_template.jinja').write_text('changed')
        with self.assertRaises(ValueError): validate_contract(profile, self.config)

    def test_metadata_cannot_be_rebound_to_another_publication_or_bank(self):
        profile = {'composition': self.contract}
        model = hashlib.sha256(b'dedicated-model-prefix-v1\0' + json.dumps(profile,
            separators=(',', ':'), sort_keys=True).encode()).hexdigest()
        key = hashlib.sha256(model.encode() + json.dumps(self.bank, separators=(',', ':')).encode()).hexdigest()
        index = {'model': model, 'records': {key: {'tokens': self.bank}}}
        spec = {'model': model, 'key': key}
        validate_publication(json.dumps(profile, separators=(',', ':'), sort_keys=True).encode(), index, spec)
        foreign = copy.deepcopy(profile)
        foreign['composition']['model_revision'] = 'foreign'
        with self.assertRaises(ValueError): validate_publication(json.dumps(foreign, separators=(',', ':'), sort_keys=True).encode(), index, spec)
        changed = copy.deepcopy(index)
        changed['records'][key]['tokens'][0] += 1
        with self.assertRaises(ValueError): validate_publication(json.dumps(profile, separators=(',', ':'), sort_keys=True).encode(), changed, spec)

    async def test_instance_hook_plain_qwen_empty_selection_and_error_paths(self):
        messages = [{'role': 'system', 'content': 'Use memory.'}, {'role': 'user', 'content': 'Q?'}]
        incoming = self.engine_input(messages)
        async def original(request): return messages, [incoming]
        handler = NS(render_chat_request=original, create_error_response=lambda error: {'error': error})
        app = NS(state=NS(openai_serving_chat=handler))
        owner = NS(gemma_contexts={'gemma-bank': self.contract}, catalog_digest='revision-a')
        other_handler = NS(render_chat_request=original)
        with patch('aimee_vllm.composition.metadata.version', return_value='0.30.0'):
            install_renderer(owner, app)
            install_renderer(owner, app)
        self.assertIs(other_handler.render_chat_request, original)
        for publication in (None, 'qwen-bank'):
            result = await handler.render_chat_request(NS(vllm_xargs={'aimee_publication': publication}))
            self.assertEqual(result, (messages, [incoming]))
        request = NS(vllm_xargs={'aimee_publication': 'gemma-bank', 'aimee_catalog_digest': 'revision-a'})
        result = await handler.render_chat_request(request)
        self.assertEqual(result[0], messages)
        self.assertEqual(result[1][0], remaining_input(incoming, self.contract))
        owner.catalog_digest = 'revision-b'
        self.assertIn('superseded', (await handler.render_chat_request(request))['error'])
        request.vllm_xargs['aimee_catalog_digest'] = 'revision-b'
        incoming['prompt_token_ids'] = [99]
        self.assertIn('error', await handler.render_chat_request(request))
        uninstall_renderer(owner)
        self.assertIs(handler.render_chat_request, original)
        self.assertFalse(hasattr(handler, '_aimee_composition_owner'))
        with patch('aimee_vllm.composition.metadata.version', return_value='0.30.0'):
            install_renderer(owner, app)
        uninstall_renderer(owner)

    def test_multimodal_and_embedding_inputs_cannot_be_shifted_as_text(self):
        incoming = self.engine_input([{'role':'system','content':'Use memory.'}, {'role':'user','content':'Q'}])
        for mutation in ({'type':'multimodal'}, {'type':'embeds'}, {'mm_placeholders':{}},
                         {'prompt_embeds':[]}, {'prompt_token_offsets':[(0,1)]},
                         {'assistant_tokens_mask':[0]}):
            with self.assertRaisesRegex(ValueError, 'layout'):
                remaining_input(dict(incoming, **mutation), self.contract)

    def test_non_prefix_stock_template_is_rejected(self):
        class Incompatible(StockTokenizer):
            def apply_chat_template(self, messages, **kwargs):
                return str(len(messages)) + super().apply_chat_template(messages, **kwargs)
        with self.assertRaisesRegex(ValueError, 'boundary'):
            prepare_contract(Incompatible(), self.root, 'Use memory.', ['Fact.'])


if __name__ == '__main__': unittest.main()
