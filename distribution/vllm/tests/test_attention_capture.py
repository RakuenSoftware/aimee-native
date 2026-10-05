import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

import torch

from aimee_vllm.attention_capture import AttentionPrefixCapture


class AttentionCaptureTests(unittest.TestCase):
    def test_variable_layer_geometry_is_preserved_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = AttentionPrefixCapture.__new__(AttentionPrefixCapture)
            capture.destination = Path(directory) / "out"
            capture.architecture = {"num_hidden_layers": 2}
            capture.tokens = [11, 12]
            capture.profile = {"weights_sha256": "a" * 64}
            from unittest.mock import Mock
            capture.adapter = Mock()
            def publish(op, **fields):
                self.assertEqual(op, "publish")
                self.assertEqual(Path(fields["payload"]).read_bytes(), expected)
                self.assertEqual([(x["heads"], x["width"]) for x in fields["segments"]],
                                 [(2, 3), (2, 3), (1, 5), (1, 5)])
                return {"root": fields["destination"]}
            capture.adapter.call.side_effect = publish
            capture.attention = {}
            expected = bytearray()
            for layer, (heads, width) in enumerate(((2, 3), (1, 5))):
                keys = torch.arange(2 * heads * width, dtype=torch.bfloat16).reshape(2, heads, width)
                values = keys + 10
                capture.attention_chunk(layer, keys, values, NS(query_start_loc=torch.tensor([0, 2])))
                for tensor in (keys, values):
                    expected.extend(tensor.transpose(0, 1).contiguous().view(torch.uint8).numpy().tobytes())
            capture.finish()
            capture.attention.pop(1)
            with self.assertRaisesRegex(RuntimeError, "coverage"):
                capture.finish()

    def test_http_worker_cannot_arm_capture(self):
        with self.assertRaisesRegex(RuntimeError, "offline"):
            AttentionPrefixCapture({}, None, [1], "text", "/unused")


if __name__ == "__main__":
    unittest.main()
