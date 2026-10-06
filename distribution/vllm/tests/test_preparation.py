import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from aimee_vllm.preparation import prepare
from aimee_vllm.composition import prepare_contract
from test_composition import StockTokenizer


class PreparationTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self, root):
        (root / 'tokenizer.json').write_text('{}')
        (root / 'tokenizer_config.json').write_text('{}')
        idle = asyncio.Event()
        idle.set()
        owner = NS(config={'native_preparation_enabled': True, 'preparation_root': str(root),
                           'model': str(root), 'serve': {'max_model_len': 2048}},
                   idle=idle, poisoned=False, paused=True, generation=2)
        request = {'op': 'prepare', 'generation': 2, 'facts': ['authorized fact'],
                   'context': '', 'destination': str(root / ('a' * 64))}
        return owner, request

    async def test_rejects_unwithdrawn_disabled_superseded_and_foreign_destinations_before_rpc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for mutation in ('active', 'disabled', 'superseded', 'foreign', 'unknown-field'):
                owner, request = self.fixture(root)
                if mutation == 'active': owner.paused = False
                if mutation == 'disabled': owner.config['native_preparation_enabled'] = False
                if mutation == 'superseded': request['generation'] = 1
                if mutation == 'foreign': request['destination'] = '/tmp/' + 'a' * 64
                if mutation == 'unknown-field': request['tokens'] = [1, 2]
                with self.assertRaises((ValueError, RuntimeError)):
                    await prepare(owner, None, request, None)
                self.assertFalse(owner.poisoned)

    async def test_exclusive_capture_waits_for_drain_and_uses_adapter_owned_rpc(self):
        with tempfile.TemporaryDirectory() as directory:
            owner, request = self.fixture(Path(directory))
            owner.idle.clear()
            calls = []
            publication = {'root': request['destination'], 'model': 'model', 'key': 'key'}
            tokenizer = StockTokenizer()
            bank_text, bank_tokens, contract = prepare_contract(tokenizer, Path(directory), '', ['authorized fact'])
            async def rpc(name, **kwargs):
                calls.append((name, kwargs))
                return [{'state': 'armed'}] if name == 'model-owned-capture' else [publication]
            async def generate(prompt, params, request_id):
                self.assertEqual(prompt, {'prompt_token_ids': bank_tokens})
                self.assertTrue(request_id.startswith('aimee-prepare-'))
                yield NS()
            engine = NS(collective_rpc=rpc, generate=generate)
            adapter = NS(description={'capture_rpc': 'model-owned-capture', 'capture_argument': 'text', 'prefix_renderer': 'stock'})
            with patch('aimee_vllm.model_adapter.ModelAdapter', return_value=adapter), \
                    patch('transformers.AutoTokenizer.from_pretrained', return_value=tokenizer):
                pending = asyncio.create_task(prepare(owner, engine, request, adapter))
                await asyncio.sleep(0)
                self.assertEqual(calls, [])
                owner.idle.set()
                result = await pending
            self.assertEqual(result['publication'], publication)
            self.assertEqual(calls[0][1]['args'], (bank_tokens, {'text':bank_text,'composition':contract}, request['destination'], True))
            self.assertEqual(calls[1][0], 'aimee_capture_finish')
            self.assertTrue(owner.paused)
            self.assertFalse(owner.poisoned)

    async def test_withdrawal_supersedes_a_pending_drain_without_touching_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            owner, request = self.fixture(Path(directory))
            owner.idle.clear()
            pending = asyncio.create_task(prepare(owner, None, request, None))
            await asyncio.sleep(0)
            owner.generation += 1
            owner.idle.set()
            with self.assertRaisesRegex(RuntimeError, 'superseded'):
                await pending
            self.assertFalse(owner.poisoned)

    async def test_adapter_renders_closed_prefix_without_stock_system_only_template(self):
        with tempfile.TemporaryDirectory() as directory:
            owner, request = self.fixture(Path(directory))
            calls = []
            def render(op, **fields):
                self.assertEqual(op, 'render_prefix')
                self.assertEqual(fields, {'context': '', 'facts': ['authorized fact']})
                return {'text': 'rust-owned-closed-prefix'}
            adapter = NS(description={'capture_rpc': 'model-owned-capture', 'capture_argument': 'context',
                                      'prefix_renderer': 'adapter'}, call=render)
            def encode(text, **kwargs):
                self.assertEqual(text, 'rust-owned-closed-prefix')
                return [1, 2]
            tokenizer = NS(encode=encode)
            async def rpc(name, **kwargs):
                calls.append((name, kwargs))
                return [{'state': 'armed'}] if name == 'model-owned-capture' else [{'root': request['destination']}]
            async def generate(*args, **kwargs):
                yield NS()
            with patch('transformers.AutoTokenizer.from_pretrained', return_value=tokenizer):
                await prepare(owner, NS(collective_rpc=rpc, generate=generate), request, adapter)
            self.assertEqual(calls[0][1]['args'], ([1, 2], '', request['destination'], True))


if __name__ == '__main__':
    unittest.main()
