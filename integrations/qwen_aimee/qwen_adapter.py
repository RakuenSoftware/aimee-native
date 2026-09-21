"""Untrained Qwen-specific native connection to the existing Aimee API.

Aimee selects records. Frozen Qwen encodes their text in a separate pass.
Its ordinary full-attention layers read those states as a separate K/V bank.
No learned adapter, oracle vectors, or memory tokens in the generation prompt.
This prototype is serial and intentionally does not optimize latency.
"""
from collections import OrderedDict
from contextlib import contextmanager
import hashlib
import json
from types import MethodType

import torch

from profiling import Profile
from native_read import NativeAimeeRead
from runtime_cues import RuntimeCueRead
from attention_bridge import AimeeAttentionBridge, forward_with_aimee


class _ReadBankCache:
    """Expose external states without inserting them into the sequence cache."""
    def __init__(self, cache, key, value):
        self.cache, self.key, self.value = cache, key, value

    def __getattr__(self, name):
        return getattr(self.cache, name)

    def update(self, key, value, layer_idx, *args, **kwargs):
        query_key, query_value = self.cache.update(key, value, layer_idx, *args, **kwargs)
        return torch.cat((self.key.to(query_key.device), query_key), dim=-2), torch.cat((self.value.to(query_value.device), query_value), dim=-2)


class QwenAimeeAdapter:
    def __init__(self, model, tokenizer, client, input_device="cpu", memory_limit=4,
                 max_memory_tokens=2048, host_memory=False, profile=False, encoding_cache_bytes=0):
        self.model, self.tokenizer, self.client = model, tokenizer, client
        self.input_device, self.memory_limit = input_device, memory_limit
        self.max_memory_tokens = max_memory_tokens
        self.host_memory = host_memory
        self.profile = Profile(profile)
        if encoding_cache_bytes < 0 or (encoding_cache_bytes and not host_memory):
            raise ValueError("encoding cache requires RAM banks and a nonnegative byte budget")
        self.encoding_cache_budget = encoding_cache_bytes
        self.encoding_cache = OrderedDict()
        self.encoding_cache_size = 0
        self.text = model.model.language_model if hasattr(model.model, "language_model") else model.model
        if self.text.config.model_type != "qwen3_5_text":
            raise ValueError("this adapter supports the installed Qwen3.5/3.8 hybrid text architecture")
        if self.text.config._attn_implementation != "eager":
            raise ValueError("prototype requires eager attention")
        self.active = None
        self.encoding = False
        self.closed = False
        self.originals = []
        self.request_layer = next(i for i, b in enumerate(self.text.layers) if b.block_type == "full_attention")
        self.attention_bridge = AimeeAttentionBridge(self)
        for index, block in enumerate(self.text.layers):
            if block.block_type != "full_attention":
                continue
            attention = block.self_attn
            original = attention.forward
            self.originals.append((attention, original))

            def forward(attention, *args, _original=original, _index=index, **kwargs):
                state = self.active
                if state is not None and state["recall_mode"] == "attention" and not self.encoding:
                    return forward_with_aimee(self, attention, *args, **kwargs)
                bank = None if self.encoding or state is None else state["banks"].get(_index)
                if bank is None:
                    return _original(*args, **kwargs)
                cache = kwargs.get("past_key_values")
                if cache is None:
                    raise RuntimeError("native memory read requires cached inference")
                keys, values = bank
                kwargs = dict(kwargs)
                kwargs["past_key_values"] = _ReadBankCache(cache, keys, values)
                mask = kwargs.get("attention_mask")
                if mask is not None:
                    if mask.dtype == torch.bool:
                        raise TypeError("expected Qwen additive attention mask")
                    extra = mask.new_zeros((*mask.shape[:-1], keys.shape[-2]))
                    kwargs["attention_mask"] = torch.cat((extra, mask), dim=-1)
                result = _original(*args, **kwargs)
                state["native_reads"] += 1
                return result

            attention.forward = MethodType(forward, attention)
        self.hook = model.register_forward_pre_hook(self._request, with_kwargs=True)
        self.native_read = NativeAimeeRead(self, after_block=1)
        self.runtime_read = RuntimeCueRead(self, after_block=1)
        self.native_hook = self.text.layers[1].register_forward_hook(
            lambda module, args, output: self.runtime_read(self.native_read(output)))

    def _request(self, module, args, kwargs):
        state = self.active
        if state is None or self.encoding:
            return
        if state["recall_mode"] in ("native_tokens", "attention"):
            ids = kwargs.get("input_ids", args[0] if args else None)
            if ids is None or ids.ndim != 2 or ids.shape[0] != 1:
                raise RuntimeError("runtime cue read requires one input_ids sequence")
            tokens = ids.detach().cpu().tolist()[0]
            step = state.get("runtime_step", -1) + 1
            phase = "prefill" if step == 0 else "decode"
            state["runtime_step"] = step
            state["runtime_frame"] = {"step": step, "phase": phase, "input_ids": tokens}
            if step == 0:
                state["runtime_prefill_ids"] = tokens
                if state["preload_query"] is not None:
                    self.recall(state["preload_query"], origin="prompt_preload",
                                query_source="latest_user_message",
                                event={"phase": "preload", "step": step})
            else:
                state["runtime_decode_ids"].extend(tokens)
            return
        if state["recall_mode"] != "prefill" or state["requested"]:
            return
        self.recall(state["query"], origin="qwen_native_prefill_hook",
                    query_source="latest_user_message")

    def recall(self, query, *, origin, query_source, event=None):
        state = self.active
        if state is None:
            raise RuntimeError("recall requires an active inference request")
        state["requested"] = True
        state["request"] = {"origin": origin, "query_source": query_source,
                            "query": query, "limit": self.memory_limit}
        event = dict(event or {})
        event.update(state["request"], native_reads_before=state["native_reads"], status="requesting")
        state["recall_events"].append(event)
        with self.profile.span("memory_search"):
            reply = self.client.search(query, self.memory_limit)
        state["aimee_response"] = reply
        event["aimee_response"] = reply
        if reply.get("windows"):
            raise RuntimeError("this initial codec does not support episode windows; refusing to drop them")
        facts = reply["facts"]
        if not all(isinstance(f, dict) and isinstance(f.get("content"), str) for f in facts):
            raise RuntimeError("unsupported Aimee fact response")
        if state["recall_mode"] in ("native_tokens", "attention"):
            # A request-local cache of Aimee-selected records. No ranking or
            # local fact selection. Repeated IDs refresh their returned content.
            for fact in facts:
                state["resident_facts"][str(fact["id"])] = fact
            facts = list(state["resident_facts"].values())
        event["bank_memory_ids"] = [f["id"] for f in facts]
        if not facts:
            event["status"] = "empty"
            return
        # Preserve every returned fact and its order. No domain-specific parsing.
        memory_text = "Authoritative memory:\n" + "\n".join(f["content"] for f in facts)
        memory_ids = self.tokenizer.encode(memory_text, add_special_tokens=False)
        if len(memory_ids) > self.max_memory_tokens:
            raise RuntimeError("Aimee response exceeds encoding capacity; refusing silent truncation")
        memory_hash = hashlib.sha256(json.dumps(memory_ids).encode()).hexdigest()
        event.update(memory_encoding_tokens=len(memory_ids), memory_encoding_sha256=memory_hash)
        if state.get("memory_encoding_sha256") == memory_hash:
            event["status"] = "bank_unchanged"
            return
        state["memory_encoding_tokens"] = len(memory_ids)
        # Only reached after a fresh authorized read. Content alone never
        # activates a cached bank. Model identity is fixed by this adapter's
        # process lifetime; no persistent or cross-model tensors are loaded.
        cache_key = hashlib.sha256(json.dumps([getattr(self.client, "authorization_id", None), memory_hash, [f["id"] for f in facts]]).encode()).hexdigest()
        use_cache = state["reuse_encoding"] and self.encoding_cache_budget > 0
        if use_cache and cache_key in self.encoding_cache:
            banks, size = self.encoding_cache.pop(cache_key)
            self.encoding_cache[cache_key] = (banks, size)
            state["banks"] = dict(banks)
            state["bank_layers"] = list(banks)
            state["bank_devices"] = {index: str(bank[0].device) for index, bank in banks.items()}
            state["memory_token_ids"] = memory_ids
            state["memory_encoding_sha256"] = memory_hash
            event.update(status="bank_reused", encoding_cache="hit")
            return
        event["encoding_cache"] = "miss" if use_cache else "disabled"
        self.encoding = True
        try:
            ids = torch.tensor([memory_ids], device=self.input_device)
            with torch.inference_mode(), self.profile.span("memory_encoding"):
                # Independent sequence and recurrent/cache state, never appended
                # to the request prompt or its cache. No learned adapter weights.
                encoded = self.model(input_ids=ids, attention_mask=torch.ones_like(ids), use_cache=True)
                state["memory_encoding_passes"] += 1
                state["memory_tokens_encoded"] += len(memory_ids)
            cache = encoded.past_key_values
            for index, block in enumerate(self.text.layers):
                if block.block_type == "full_attention":
                    layer = cache.layers[index]
                    keys, values = layer.keys.detach(), layer.values.detach()
                    if self.host_memory:
                        with self.profile.span("bank_to_host"):
                            keys, values = keys.cpu(), values.cpu()
                    state["banks"][index] = (keys, values)
            state["bank_layers"] = list(state["banks"])
            state["bank_devices"] = {index: str(bank[0].device) for index, bank in state["banks"].items()}
            state["memory_token_ids"] = memory_ids
            state["memory_encoding_sha256"] = memory_hash
            event["status"] = "bank_updated"
            if use_cache:
                size = sum(t.numel()*t.element_size() for bank in state["banks"].values() for t in bank)
                if size <= self.encoding_cache_budget:
                    while self.encoding_cache_size + size > self.encoding_cache_budget:
                        _, (_, removed) = self.encoding_cache.popitem(last=False)
                        self.encoding_cache_size -= removed
                    self.encoding_cache[cache_key] = (dict(state["banks"]), size)
                    self.encoding_cache_size += size
        finally:
            self.encoding = False

    @contextmanager
    def request(self, query=None, *, recall_mode="prefill", decode_recall=True,
                cue_window_tokens=64, decode_cue_boundary="whitespace", preload_query=None, reuse_encoding=True):
        if self.closed or self.active is not None:
            raise RuntimeError("adapter closed or request already active")
        if recall_mode not in ("prefill", "native", "native_tokens", "attention"):
            raise ValueError("unknown recall mode")
        if recall_mode in ("native", "native_tokens", "attention") and query is not None:
            raise ValueError("native read does not accept an external query")
        if preload_query is not None and (recall_mode != "attention" or
                not isinstance(preload_query, str) or not preload_query.strip()):
            raise ValueError("prompt preload requires attention mode and a nonempty query")
        if type(decode_recall) is not bool or type(cue_window_tokens) is not int or not 1 <= cue_window_tokens <= 512:
            raise ValueError("invalid runtime recall settings")
        if decode_cue_boundary not in ("whitespace", "every_token"):
            raise ValueError("invalid decode cue boundary")
        if recall_mode == "prefill" and (not isinstance(query, str) or not query.strip()):
            raise ValueError("prefill recall requires a query")
        state = {"reuse_encoding": reuse_encoding, "memory_encoding_passes": 0, "memory_tokens_encoded": 0, "query": query, "requested": False, "banks": {}, "native_reads": 0,
                 "preload_query": preload_query,
                 "memory_encoding_tokens": 0, "bank_layers": [], "recall_mode": recall_mode,
                 "decode_recall": decode_recall, "cue_window_tokens": cue_window_tokens,
                 "decode_cue_boundary": decode_cue_boundary,
                 "runtime_decode_ids": [], "recall_events": [], "resident_facts": {}}
        self.active = state
        self.profile.events = []
        try:
            begin = getattr(self.client, "begin_request", None)
            if begin is not None:
                with self.profile.span("pin_image"):
                    state["source_view"] = begin()
            state["bank_residence"] = "ram" if self.host_memory else "model_devices"
            yield state
        finally:
            state["encoding_cache_bytes"] = self.encoding_cache_size
            state["profile_events"] = self.profile.events
            state["banks"].clear()
            self.active = None

    def close(self):
        if self.active is not None:
            raise RuntimeError("cannot close during a request")
        if not self.closed:
            self.hook.remove()
            self.native_hook.remove()
            for attention, original in self.originals:
                attention.forward = original
            self.encoding_cache.clear()
            self.encoding_cache_size = 0
            self.closed = True
