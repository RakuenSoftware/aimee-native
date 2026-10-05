"""Private preparation-only lazy checkpoint weights for supported offload hooks.

The serving hot path does not import this module. FP32 expansion happens during
memory preparation, never when a published memory is consumed.
"""
from collections import OrderedDict
from collections.abc import Mapping
import json
from pathlib import Path

import torch
from safetensors import safe_open


class CheckpointWeights(Mapping):
    """Expose original safetensors as ephemeral compute-dtype CPU tensors.

    Handles keep source mappings available; expanded tensors are not cached.
    Accelerate's normal offload hooks own the tensors while a module executes.
    Use one instance per serialized preparation worker.
    """
    def __init__(self, root, dtype=torch.float32, max_open_shards=2, aliases=None):
        self.root = Path(root)
        self.index = json.loads((self.root / 'model.safetensors.index.json').read_text())['weight_map']
        self.dtype = dtype
        if dtype not in (torch.float32, torch.bfloat16):
            raise ValueError('unsupported preparation compute dtype')
        if max_open_shards < 1:
            raise ValueError('at least one source shard handle is required')
        if any(Path(name).name != name for name in self.index.values()):
            raise ValueError('checkpoint shard must be local to the checkpoint')
        self.limit = max_open_shards
        self.aliases = dict(aliases or {})
        if set(self.aliases) & set(self.index) or any(value not in self.index for value in self.aliases.values()):
            raise ValueError('aliases must name an existing canonical checkpoint tensor')
        self.handles = OrderedDict()
        self.reads = 0
        self.expanded_bytes = 0

    def __iter__(self):
        yield from self.index
        yield from self.aliases

    def __len__(self):
        return len(self.index) + len(self.aliases)

    def __getitem__(self, name):
        canonical = self.aliases.get(name, name)
        shard = self.index[canonical]
        if shard in self.handles:
            handle = self.handles.pop(shard)
        else:
            if len(self.handles) == self.limit:
                _, old = self.handles.popitem(last=False)
                old.__exit__(None, None, None)
            handle = safe_open(self.root / shard, framework='pt', device='cpu')
            handle.__enter__()
        self.handles[shard] = handle
        original = handle.get_tensor(canonical)
        tensor = original.to(self.dtype) if original.is_floating_point() else original
        self.reads += 1
        self.expanded_bytes += tensor.numel() * tensor.element_size()
        return tensor

    def close(self):
        while self.handles:
            _, handle = self.handles.popitem()
            handle.__exit__(None, None, None)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
