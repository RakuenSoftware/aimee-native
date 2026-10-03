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


if __name__ == '__main__':
    unittest.main()
