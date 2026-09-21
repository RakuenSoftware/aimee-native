"""P0 only: frozen-model injection and resident sequence banks, no Aimee I/O."""
from contextlib import contextmanager
from dataclasses import dataclass
import math

import torch
from torch import nn


@dataclass(frozen=True)
class SequenceMemory:
    ids: tuple[int, ...]
    generation: int
    keys: torch.Tensor
    values: torch.Tensor


class EngramLayer(nn.Module):
    def __init__(self, hidden_width, value_width=2048, attention_width=256):
        super().__init__()
        self.norm = nn.RMSNorm(hidden_width, eps=1e-6)
        self.query = nn.Linear(hidden_width, attention_width, bias=False)
        self.key = nn.Linear(value_width, attention_width, bias=False)
        self.value = nn.Linear(value_width, hidden_width, bias=False)
        self.output = nn.Linear(hidden_width, hidden_width, bias=False)
        self.gate = nn.Linear(hidden_width, 1)
        # Zero only the output: the first update opens the channel, subsequent
        # updates can reach keys/values. Zeroing both alpha and output deadlocks.
        nn.init.zeros_(self.output.weight)

    def prepare(self, ids, vectors, generation):
        """Called once before forward/prefill, never by the decode hook.

        Training retains this graph for one backward. Inference callers use
        no_grad and retain the bank for the entire sequence.
        """
        if vectors.ndim != 2 or vectors.shape[0] != len(ids):
            raise ValueError("bank requires one vector per admitted ID")
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate bank IDs")
        return SequenceMemory(tuple(ids), generation, self.key(vectors), self.value(vectors))

    def forward(self, hidden, bank):
        if bank is None or not bank.ids:
            return hidden
        # Optional FP32 trainable interface with a frozen BF16 base. Keep Adam
        # parameters/moments in FP32 and cast only at the residual boundary.
        base_dtype = hidden.dtype
        hidden = hidden.to(self.query.weight.dtype)
        q = self.query(self.norm(hidden))
        scores = (q @ bank.keys.T) / math.sqrt(q.shape[-1])
        weights = scores.float().softmax(dim=-1).to(q.dtype)
        residual = self.output(weights @ bank.values)
        return (hidden + self.gate(hidden).sigmoid() * residual).to(base_dtype)


class OracleValues(nn.Module):
    """Synthetic P0 table. Validity is supplied, not decided, by this module."""
    def __init__(self, memory_ids, value_width, scope="synthetic.p0", generation=1):
        super().__init__()
        if len(set(memory_ids)) != len(memory_ids):
            raise ValueError("duplicate memory IDs")
        self.row = {mid: i for i, mid in enumerate(memory_ids)}
        self.scope = scope
        self.generation = generation
        self.values = nn.Parameter(torch.randn(len(memory_ids), value_width) * 0.02)

    def prepare(self, layer, candidates, active_ids, scope, generation, k=16):
        if scope != self.scope or generation != self.generation:
            raise ValueError("scope/generation mismatch")
        # IDs arrive from an oracle in P0. A future image reader replaces this
        # admission step. No policy or global table access occurs in forward.
        ids = tuple(dict.fromkeys(mid for mid in candidates if mid in active_ids))
        if len(ids) > k:
            raise ValueError("oracle bank exceeds K; refusing silent truncation")
        rows = [self.row[mid] for mid in ids]  # Unknown active IDs fail closed.
        return layer.prepare(ids, self.values[rows], generation)


class FrozenQwenEngram:
    """Single-request research wrapper. Not a concurrent serving runtime.

    The hook is installed on the actual HF Qwen block, avoiding a model replica.
    A bank must remain bound through backward if checkpoint recomputation is used.
    """
    def __init__(self, base, value_width=2048, attention_width=256, after_block=1):
        base.requires_grad_(False)
        base.eval()
        self.base = base
        text = base.model
        if hasattr(text, "language_model"):
            text = text.language_model
        config = text.config
        if config.model_type != "qwen3_5_text":
            raise ValueError("P0 wrapper supports the verified Qwen3.5 text architecture")
        block = text.layers[after_block]
        parameter = next(block.parameters())
        self.layer = EngramLayer(config.hidden_size, value_width, attention_width).to(
            device=parameter.device, dtype=parameter.dtype)
        self.bank = None
        self._bound = False
        self.handle = block.register_forward_hook(self._inject)

    def _inject(self, module, inputs, output):
        if not isinstance(output, torch.Tensor):
            raise TypeError("Qwen decoder output contract changed")
        return self.layer(output, self.bank)

    @contextmanager
    def using(self, bank):
        if self._bound:
            raise RuntimeError("P0 wrapper does not support nested/concurrent requests")
        self._bound, self.bank = True, bank
        try:
            yield
        finally:
            self.bank, self._bound = None, False

    def close(self):
        if self._bound:
            raise RuntimeError("cannot detach during a request")
        self.handle.remove()
