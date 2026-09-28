"""Reduced architectures: FP32 hidden states/cache parity using real HF models.

These exercise preparation mechanics, not pretrained-model quality.
"""
import json
from pathlib import Path
import tempfile
import unittest

import torch
from accelerate import cpu_offload, init_empty_weights
from safetensors.torch import save_file
from transformers import Gemma4TextConfig, Gemma4TextModel, Qwen3_5TextConfig, Qwen3_5TextModel
from checkpoint_weights import CheckpointWeights


class TransformerPreparationParity(unittest.TestCase):
    def test_gemma_moe_and_qwen_hybrid_hidden_states_and_native_cache(self):
        torch.set_num_threads(2)
        configs = [
            (Gemma4TextModel, Gemma4TextConfig(
                vocab_size=64, hidden_size=32, intermediate_size=48,
                num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2,
                head_dim=8, global_head_dim=8, sliding_window=32,
                layer_types=['sliding_attention', 'full_attention'],
                hidden_size_per_layer_input=0, vocab_size_per_layer_input=64,
                enable_moe_block=True, num_experts=4, top_k_experts=2,
                moe_intermediate_size=16), True, []),
            (Qwen3_5TextModel, Qwen3_5TextConfig(
                vocab_size=64, hidden_size=32, intermediate_size=48,
                num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2,
                head_dim=8, layer_types=['linear_attention', 'full_attention'],
                linear_key_head_dim=8, linear_value_head_dim=8,
                linear_num_key_heads=2, linear_num_value_heads=4,
                rope_parameters={'rope_type': 'default', 'rope_theta': 10000.0,
                    'partial_rotary_factor': 1.0, 'mrope_section': [1, 1, 2],
                    'mrope_interleaved': True}), False, ['Qwen3_5GatedDeltaNet']),
        ]
        for cls, config, negative_positions, preload in configs:
            with self.subTest(model=cls.__name__), tempfile.TemporaryDirectory() as directory:
                torch.manual_seed(20260928)
                config._attn_implementation = 'eager'
                reference = cls(config).eval()
                # Match checkpoint BF16 values while leaving computed rotary
                # buffers at their original FP32 precision.
                state = {name: (value.bfloat16() if value.is_floating_point() else value)
                         for name, value in reference.state_dict().items()}
                reference.load_state_dict(state)
                root = Path(directory)
                prefix = 'model.language_model.'
                saved = {prefix + name: value.contiguous() for name, value in state.items()}
                save_file(saved, root / 'model.safetensors')
                (root / 'model.safetensors.index.json').write_text(json.dumps({
                    'weight_map': {name: 'model.safetensors' for name in saved}}))
                with init_empty_weights():
                    lazy = cls(config).eval()
                aliases = {name: prefix + name for name in state}
                with CheckpointWeights(root, aliases=aliases) as weights:
                    cpu_offload(lazy, execution_device=torch.device('cpu'),
                                state_dict=weights, preload_module_classes=preload)
                    for length in (5, 11):
                        ids = torch.arange(3, 3 + length).unsqueeze(0)
                        positions = torch.arange(-length, 0) if negative_positions else torch.arange(length)
                        args = dict(input_ids=ids, position_ids=positions.unsqueeze(0),
                                    attention_mask=torch.ones_like(ids), use_cache=True)
                        with torch.inference_mode():
                            expected = reference(**args)
                            actual = lazy(**args)
                        self.assertTrue(torch.isfinite(actual.last_hidden_state).all())
                        self.assertTrue(torch.equal(actual.last_hidden_state, expected.last_hidden_state))
                        compared = 0
                        for wanted, got in zip(expected.past_key_values.layers, actual.past_key_values.layers):
                            if getattr(wanted, 'keys', None) is not None:
                                self.assertTrue(torch.equal(got.keys, wanted.keys))
                                self.assertTrue(torch.equal(got.values, wanted.values))
                                compared += 1
                        self.assertGreater(compared, 0)
                        self.assertTrue(all(p.device.type == 'meta' for p in lazy.parameters()))


if __name__ == '__main__':
    unittest.main()
