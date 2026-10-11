"""Research attention-bank attachment at an immutable history checkpoint.

Attention-only, default RoPE. No claim of installed serving authorization.
The public-history checkpoint never contains bank-conditioned task state.
"""
import hashlib
import time


def tensor_digest(pairs):
    h = hashlib.sha256()
    for pair in pairs:
        for t in pair:
            h.update(t.detach().contiguous().view(-1).view(__import__('torch').uint8).cpu().numpy().tobytes())
    return h.hexdigest()


class ScopedCache:
    def __init__(self, model):
        import torch
        from transformers.cache_utils import DynamicCache
        self.torch, self.Cache, self.model = torch, DynamicCache, model
        assert model.config.model_type == 'qwen3'
        assert not model.config.use_sliding_window
        rope = getattr(model.config, 'rope_parameters', None) or getattr(model.config, 'rope_scaling', None) or {}
        assert rope.get('rope_type', 'default') == 'default', 'Only fixed default RoPE qualified'
        assert all(p.device.type == 'cuda' for p in model.parameters())
        self.counters = {'prefill_tokens': 0, 'decode_tokens': 0}

    def pairs(self, cache):
        return [(x.keys, x.values) for x in cache.layers]

    def wrap(self, pairs):
        # New layer wrappers reference immutable checkpoint tensors. Cache.update
        # replaces each wrapper's tensor; it cannot mutate the checkpoint owner.
        cache = self.Cache(config=self.model.config)
        for layer, (k, v) in zip(cache.layers, pairs, strict=True):
            assert k.device.type == v.device.type == 'cuda'
            layer.lazy_initialization(k, v)
            layer.keys, layer.values = k, v
        return cache

    def forward(self, ids, cache=None):
        torch = self.torch
        assert ids
        n = cache.get_seq_length() if cache is not None else 0
        t = torch.tensor([ids], dtype=torch.long, device='cuda')
        self.counters['prefill_tokens'] += len(ids)
        return self.model(input_ids=t, past_key_values=cache, use_cache=True,
                          position_ids=torch.arange(n, n+len(ids), device='cuda')[None],
                          logits_to_keep=1)

    def prefill(self, ids, checkpoint=None):
        cache = self.wrap(self.pairs(checkpoint)) if checkpoint is not None else None
        return self.forward(ids, cache).past_key_values

    def attach(self, checkpoint, bank):
        """Append a repositioned independently prepared bank, without history prefill.

        Re-rotation changes position only. It does not supply missing attention
        from the bank to the earlier history. That is an empirical fidelity test.
        """
        torch = self.torch
        h, m = checkpoint.get_seq_length(), bank.get_seq_length()
        pos = torch.arange(m, device='cuda')[None]
        probe = self.pairs(bank)[0][0]
        oc, os = self.model.model.rotary_emb(probe, pos)
        nc, ns = self.model.model.rotary_emb(probe, pos+h)
        norm = oc.square()+os.square()
        cosine = ((nc*oc+ns*os)/norm).unsqueeze(1)
        sine = ((ns*oc-nc*os)/norm).unsqueeze(1)
        pairs = []
        for (hk, hv), (bk, bv) in zip(self.pairs(checkpoint), self.pairs(bank), strict=True):
            half = bk.shape[-1]//2
            rotated = bk*cosine + torch.cat((-bk[..., half:], bk[..., :half]), -1)*sine
            pairs.append((torch.cat((hk, rotated), -2), torch.cat((hv, bv), -2)))
        return self.wrap(pairs)

    def answer(self, ids, cache, tokenizer, max_tokens=32):
        torch = self.torch
        torch.cuda.synchronize(); start = time.perf_counter()
        out = self.forward(ids, cache)
        torch.cuda.synchronize(); first = time.perf_counter()-start
        query_cache = self.wrap(self.pairs(out.past_key_values))
        generated = []
        for i in range(max_tokens):
            token = int(out.logits[0, -1].argmax())
            if token in {tokenizer.eos_token_id, 151645, 151643}:
                break
            generated.append(token)
            if i+1 == max_tokens:
                break
            out = self.model(input_ids=torch.tensor([[token]], device='cuda'),
                             past_key_values=out.past_key_values, use_cache=True,
                             logits_to_keep=1)
            self.counters['decode_tokens'] += 1
        torch.cuda.synchronize()
        return {'answer': tokenizer.decode(generated, skip_special_tokens=True).strip(),
                'output_ids': generated, 'inference_first_seconds': first,
                'inference_end_seconds': time.perf_counter()-start,
                'query_cache': query_cache}
