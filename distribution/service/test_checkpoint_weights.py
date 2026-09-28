"""Exercise real Accelerate offload hooks against an ordinary FP32 reference."""
import json
from pathlib import Path
import tempfile
import unittest

import torch
from accelerate import cpu_offload, init_empty_weights
from safetensors.torch import save_file
from checkpoint_weights import CheckpointWeights


class Network(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.first = torch.nn.Linear(16, 32)
        self.second = torch.nn.Linear(32, 8)

    def forward(self, value):
        return self.second(torch.tanh(self.first(value)))


class LazyPreparationWeights(unittest.TestCase):
    def test_real_offload_matches_full_fp32_and_releases_parameters(self):
        torch.set_num_threads(2)
        torch.manual_seed(20260928)
        reference = Network().bfloat16().float().eval()
        state = {name: value.bfloat16() for name, value in reference.state_dict().items()}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = {}
            for number, (name, value) in enumerate(state.items()):
                shard = f'{number}.safetensors'
                save_file({name: value}, root / shard)
                index[name] = shard
            (root / 'model.safetensors.index.json').write_text(json.dumps({'weight_map': index}))
            with init_empty_weights():
                lazy = Network().eval()
            with CheckpointWeights(root, max_open_shards=1) as weights:
                cpu_offload(lazy, execution_device=torch.device('cpu'), offload_buffers=True, state_dict=weights)
                for batch in (1, 7, 3):
                    values = torch.randn(batch, 16)
                    with torch.inference_mode():
                        actual = lazy(values)
                        expected = reference(values)
                    self.assertTrue(torch.equal(actual, expected))
                    self.assertTrue(all(p.device.type == 'meta' for p in lazy.parameters()))
                    self.assertLessEqual(len(weights.handles), 1)
                self.assertEqual(weights.reads, 12)
            self.assertFalse(weights.handles)

    def test_tied_alias_and_integral_dtype_survive_source_handle_eviction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_file({'embedding': torch.arange(8).bfloat16()}, root / 'a.safetensors')
            save_file({'counter': torch.tensor([4], dtype=torch.int64)}, root / 'b.safetensors')
            (root / 'model.safetensors.index.json').write_text(json.dumps({'weight_map': {
                'embedding': 'a.safetensors', 'counter': 'b.safetensors'}}))
            with CheckpointWeights(root, max_open_shards=1, aliases={'head': 'embedding'}) as weights:
                held = weights['head']
                self.assertEqual(weights['counter'].dtype, torch.int64)
                self.assertTrue(torch.equal(held, torch.arange(8).float()))
                self.assertTrue(torch.equal(weights['embedding'], held))


if __name__ == '__main__':
    unittest.main()
