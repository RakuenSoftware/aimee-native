"""Qwen attention request -> existing Aimee API -> Qwen attention response.

The request is Qwen's actual projected, normalized, rotated attention query.
The existing text-search API requires translation: resolve the content addressed
by that query against its keys, preserving exact lexical spans. No independent
query generator, token-stream trigger, learned weights, or memory ranking.
"""
from dataclasses import dataclass
import hashlib
import re

import torch
from transformers.models.qwen3_5.modeling_qwen3_5 import (
    apply_rotary_pos_emb, eager_attention_forward, repeat_kv,
)


@dataclass(frozen=True)
class NativeAttentionRequest:
    query: torch.Tensor
    keys: torch.Tensor
    values: torch.Tensor
    mask: torch.Tensor | None
    layer: int
    scaling: float


@dataclass(frozen=True)
class NativeAttentionMemory:
    keys: torch.Tensor
    values: torch.Tensor


def token_byte_spans(tokenizer, ids):
    # Qwen's byte-level vocabulary gives exact offsets even when generated
    # token segmentation is not the tokenizer's canonical re-encoding.
    byte_values = list(range(33, 127)) + list(range(161, 173)) + list(range(174, 256))
    characters = byte_values.copy()
    extra = 0
    for value in range(256):
        if value not in byte_values:
            byte_values.append(value)
            characters.append(256 + extra)
            extra += 1
    decoder = {chr(c): b for b, c in zip(byte_values, characters)}
    pieces = [bytes(decoder[c] for c in token) for token in tokenizer.convert_ids_to_tokens(ids)]
    raw = b"".join(pieces)
    text = raw.decode("utf-8", errors="replace")
    if text != tokenizer.decode(ids, skip_special_tokens=False):
        raise RuntimeError("unsupported Qwen token address encoding")
    offsets = []
    end = 0
    for piece in pieces:
        offsets.append((end, end + len(piece)))
        end += len(piece)
    return text, offsets


def addressed_query(request, tokenizer, sources, groups, max_words=12):
    """Translate attention addresses to lexical spans for memory.search.

    sources is the token-address metadata for the corresponding K/V slots.
    It is not itself the query: Qwen's query tensor selects its addressed words.
    """
    keys = repeat_kv(request.keys, groups)
    weights = (request.query[:, :, -1:, :].float() @ keys.float().transpose(-2, -1)) * request.scaling
    if request.mask is not None:
        weights = weights + request.mask[:, :, -1:, :].float()
    scores = weights.softmax(dim=-1).mean(dim=1)[0, 0].detach().cpu().tolist()
    spans = []
    offset = 0
    special = set(tokenizer.all_special_ids)
    special.update(i for i, token in getattr(tokenizer, "added_tokens_decoder", {}).items()
                   if token.special)
    for source, ids in sources:
        text, offsets = token_byte_spans(tokenizer, ids)
        for word in re.finditer(r"\w+(?:[-.]\w+)*", text):
            start = len(text[:word.start()].encode("utf-8"))
            end = len(text[:word.end()].encode("utf-8"))
            positions = [i for i, (a, b) in enumerate(offsets)
                         if a < end and b > start and ids[i] not in special]
            if not positions:
                continue
            spans.append({"text": word.group(), "source": source,
                          "positions": [offset+i for i in positions],
                          "score": sum(scores[offset+i] for i in positions)})
        offset += len(ids)
    if offset != len(scores):
        raise RuntimeError("native address metadata differs from attention key count")
    selected = sorted(spans, key=lambda s: s["score"], reverse=True)[:max_words]
    selected.sort(key=lambda s: s["positions"][0])
    return " ".join(s["text"] for s in selected), selected


class AimeeAttentionBridge:
    """Stateless model-specific translation. Aimee owns memory selection."""
    def __init__(self, adapter):
        self.adapter = adapter

    def read(self, request, attention):
        adapter = self.adapter
        state = adapter.active
        frame = state["runtime_frame"]
        # This call originates in Qwen's attention forward, after Q/K projection.
        # Tokens only identify the content of the key slots Qwen is addressing.
        sources = [("sequence", state["runtime_prefill_ids"] + state["runtime_decode_ids"])]
        bank = state["banks"].get(request.layer)
        lookup = request
        if bank is not None:
            keys, values = bank
            with adapter.profile.span("bank_to_device"):
                keys, values = keys.to(request.keys.device), values.to(request.values.device)
            mask = request.mask
            if mask is not None:
                mask = torch.cat((mask.new_zeros((*mask.shape[:-1], keys.shape[-2])), mask), dim=-1)
            lookup = NativeAttentionRequest(request.query,
                torch.cat((keys, request.keys), dim=-2),
                torch.cat((values, request.values), dim=-2), mask, request.layer, request.scaling)
            sources.insert(0, ("aimee", state["memory_token_ids"]))
        with adapter.profile.span("query_translation"):
            query, selected = addressed_query(lookup, adapter.tokenizer, sources, attention.num_key_value_groups)
        if query:
            event = {"phase": frame["phase"], "step": frame["step"], "attention_layer": request.layer,
                "native_query_shape": list(request.query.shape),
                "native_query_sha256": hashlib.sha256(request.query.detach().float().cpu().contiguous().numpy().tobytes()).hexdigest(),
                "addressed_spans": selected, "native_key_count": request.keys.shape[-2],
                "bank_memory_ids_before": [f["id"] for f in state["resident_facts"].values()]}
            adapter.recall(query, origin="qwen_attention_query", query_source="projected_attention_query",
                           event=event)
        bank = state["banks"].get(request.layer)
        return None if bank is None else NativeAttentionMemory(*bank)


def forward_with_aimee(adapter, attention, hidden_states, position_embeddings,
                       attention_mask=None, past_key_values=None, **kwargs):
    """Qwen's own attention math, with its native read connected to the bridge."""
    input_shape = hidden_states.shape[:-1]
    hidden_shape = (*input_shape, -1, attention.head_dim)
    query, gate = torch.chunk(attention.q_proj(hidden_states).view(
        *input_shape, -1, attention.head_dim * 2), 2, dim=-1)
    gate = gate.reshape(*input_shape, -1)
    query = attention.q_norm(query.reshape(hidden_shape)).transpose(1, 2)
    keys = attention.k_norm(attention.k_proj(hidden_states).view(hidden_shape)).transpose(1, 2)
    values = attention.v_proj(hidden_states).view(hidden_shape).transpose(1, 2)
    query, keys = apply_rotary_pos_emb(query, keys, *position_embeddings)
    if past_key_values is None:
        raise RuntimeError("native attention bridge requires cached inference")
    keys, values = past_key_values.update(keys, values, attention.layer_idx)
    state = adapter.active
    bank = state["banks"].get(attention.layer_idx)
    frame = state["runtime_frame"]
    if (attention.layer_idx == adapter.request_layer
            and (frame["phase"] == "prefill" or state["decode_recall"])):
        response = adapter.attention_bridge.read(NativeAttentionRequest(
            query, keys, values, attention_mask, attention.layer_idx, attention.scaling), attention)
        bank = None if response is None else (response.keys, response.values)
    if bank is not None:
        memory_keys, memory_values = bank
        with adapter.profile.span("bank_to_device"):
            memory_keys = memory_keys.to(keys.device)
            memory_values = memory_values.to(values.device)
        keys = torch.cat((memory_keys, keys), dim=-2)
        values = torch.cat((memory_values, values), dim=-2)
        if attention_mask is not None:
            prefix = attention_mask.new_zeros((*attention_mask.shape[:-1], memory_keys.shape[-2]))
            attention_mask = torch.cat((prefix, attention_mask), dim=-1)
        state["native_reads"] += 1
    output, weights = eager_attention_forward(attention, query, keys, values, attention_mask,
        scaling=attention.scaling, dropout=0.0, **kwargs)
    output = output.reshape(*input_shape, -1).contiguous() * torch.sigmoid(gate)
    return attention.o_proj(output), weights
