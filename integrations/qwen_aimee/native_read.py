"""Experimental activation-to-query read inside Qwen, with no trained weights.

The existing Aimee endpoint accepts text, not Qwen vectors. Translate early
residual states through the frozen input embedding dictionary. This is a
lexical readout hypothesis, not a learned semantic query head or recall policy.
It never reads input token IDs, chat messages, or a caller-supplied query.
"""
import hashlib
import weakref

import torch
from torch import nn
from torch.nn import functional as F


class NativeAimeeRead(nn.Module):
    def __init__(self, adapter, after_block=1, chunk_size=4096):
        super().__init__()
        # References do not register/copy the base model's parameters here.
        self._adapter = weakref.ref(adapter)
        self.after_block = after_block
        self.chunk_size = chunk_size

    def forward(self, hidden):
        adapter = self._adapter()
        state = adapter.active
        if (state is None or adapter.encoding or state["recall_mode"] != "native"
                or state["requested"] or "native_query_state" in state):
            return hidden
        if hidden.ndim != 3 or hidden.shape[0] != 1:
            raise RuntimeError("native read supports one unpadded sequence at a time")
        # Exactly one read on the first forward pass. Decode consumes the bank;
        # it does not call Aimee again. This schedule is explicit, not learned.
        embedding = adapter.text.embed_tokens.weight.detach()
        states = hidden[0].detach().to(device=embedding.device, dtype=torch.float32)
        state["native_query_state"] = {
            "after_block": self.after_block,
            "shape": list(hidden.shape),
            "sha256": hashlib.sha256(states.cpu().contiguous().numpy().tobytes()).hexdigest(),
            "readout": "nearest_frozen_input_embedding_cosine_v1",
            "schedule": "first_forward_only",
        }
        normalized = F.normalize(states, dim=-1)
        best_scores = states.new_full((states.shape[0],), float("-inf"))
        best_ids = torch.zeros(states.shape[0], dtype=torch.long, device=states.device)
        with torch.inference_mode():
            for start in range(0, embedding.shape[0], self.chunk_size):
                rows = F.normalize(embedding[start:start+self.chunk_size].float(), dim=-1)
                scores, indices = (normalized @ rows.T).max(dim=-1)
                better = scores > best_scores
                best_ids = torch.where(better, indices + start, best_ids)
                best_scores = torch.maximum(best_scores, scores)
        ids = best_ids.cpu().tolist()
        query = adapter.tokenizer.decode(ids, skip_special_tokens=True).strip()
        state["native_query_state"].update(readout_token_ids=ids,
            cosine_scores=best_scores.cpu().tolist(), query=query)
        if not query:
            state["native_query_state"]["empty_query"] = True
            return hidden
        adapter.recall(query, origin="qwen_native_read_layer",
                       query_source="block_hidden_states")
        return hidden
