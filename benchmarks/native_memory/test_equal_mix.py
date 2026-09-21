"""Check the selector bypass and retained injection arithmetic."""
import unittest
from unittest.mock import patch

import torch

from engram import EngramLayer
from run_equal_mix import equal_forward


class EqualMixTests(unittest.TestCase):
    def test_equal_values_ignore_keys_and_selector_keep_gate_and_output(self):
        torch.manual_seed(7)
        layer = EngramLayer(8, 4, 2)
        torch.nn.init.normal_(layer.output.weight)
        hidden = torch.randn(1, 3, 8)
        bank = layer.prepare([5, 6], torch.randn(2, 4), 1)
        expected = hidden + layer.gate(hidden).sigmoid() * layer.output(
            (0.5 * bank.values[0] + 0.5 * bank.values[1]).expand_as(hidden))
        bank.keys.fill_(float("nan"))
        with patch.object(layer.query, "forward", side_effect=AssertionError("query called")), \
             patch.object(layer.norm, "forward", side_effect=AssertionError("norm called")):
            actual = equal_forward(layer, hidden, bank)
        torch.testing.assert_close(actual, expected)

    def test_empty_bank_is_identity_and_wrong_count_is_rejected(self):
        layer = EngramLayer(8, 4, 2)
        hidden = torch.randn(1, 1, 8)
        self.assertIs(equal_forward(layer, hidden, None), hidden)
        with self.assertRaises(ValueError):
            equal_forward(layer, hidden, layer.prepare([5], torch.randn(1, 4), 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
