"""GGUF norm scales must be restored before Qwen's zero-centered RMSNorm."""
from types import SimpleNamespace
import unittest

import numpy as np

from gguf_weights import GgufWeights


class QwenNormRestoration(unittest.TestCase):
    def test_zero_centered_norms_and_ssm_norm_differ(self):
        weights = object.__new__(GgufWeights)
        weights.config = SimpleNamespace(linear_num_key_heads=4,
                                         linear_num_value_heads=4)
        effective = np.array([0.75, 1.25], dtype=np.float32)
        for name in (
                'model.language_model.layers.0.input_layernorm.weight',
                'model.language_model.layers.0.post_attention_layernorm.weight',
                'model.language_model.layers.3.self_attn.q_norm.weight',
                'model.language_model.layers.3.self_attn.k_norm.weight',
                'model.language_model.norm.weight'):
            with self.subTest(name=name):
                np.testing.assert_array_equal(weights._qwen_restore(name, effective),
                                              np.array([-0.25, 0.25], dtype=np.float32))
        np.testing.assert_array_equal(weights._qwen_restore(
            'model.language_model.layers.0.linear_attn.norm.weight', effective), effective)


class GemmaMoERestoration(unittest.TestCase):
    def test_moe_and_per_layer_tensors_have_checkpoint_targets(self):
        expected = {
            'layer_output_scale.weight': 'layer_scalar',
            'ffn_down_exps.weight': 'experts.down_proj',
            'ffn_gate_up_exps.weight': 'experts.gate_up_proj',
            'post_ffw_norm_1.weight': 'post_feedforward_layernorm_1.weight',
            'post_ffw_norm_2.weight': 'post_feedforward_layernorm_2.weight',
            'pre_ffw_norm_2.weight': 'pre_feedforward_layernorm_2.weight',
            'ffn_down_exps.scale': 'router.per_expert_scale',
            'ffn_gate_inp.weight': 'router.proj.weight',
            'ffn_gate_inp.scale': 'router.scale',
        }
        for gguf, checkpoint in expected.items():
            with self.subTest(gguf=gguf):
                self.assertEqual(GgufWeights._gemma_fallback_target('blk.29.' + gguf),
                                 'layers.29.' + checkpoint)
        self.assertIsNone(GgufWeights._gemma_fallback_target('blk.29.unrelated'))


if __name__ == '__main__':
    unittest.main()
