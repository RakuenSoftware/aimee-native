"""Private CPU preparation worker; never distribute with the serving client."""
import argparse
import json
import sys
import time
from pathlib import Path
import torch
from transformers import AutoTokenizer, Gemma4UnifiedForConditionalGeneration
from publisher import publish


class GemmaCompiler:
    """Retain the model and optionally one scope-bound, Rust-planned prefix cache."""
    def __init__(self, model, max_memory_tokens=1024, threads=12, reuse_library=None,
                 compute_dtype='bfloat16'):
        torch.set_num_threads(threads)
        if compute_dtype not in ('bfloat16', 'float32'):
            raise ValueError('unsupported CPU preparation dtype')
        self.compute_dtype = getattr(torch, compute_dtype)
        self.max_memory_tokens = max_memory_tokens
        self.tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
        self.model_path = model
        self.model = None
        self.cache = None
        self.last_metrics = {}
        from reuse import ReusePlanner
        self.planner = ReusePlanner(reuse_library, max_memory_tokens) if reuse_library else None

    def load(self):
        if self.model is None:
            self.model = Gemma4UnifiedForConditionalGeneration.from_pretrained(
                self.model_path, local_files_only=True, dtype=self.compute_dtype,
                device_map='cpu', attn_implementation='eager').eval()

    def encode(self, request):
        started = time.perf_counter()
        facts = request['response']['facts']
        records = request['identity']['records']
        if not facts or len(facts) != len(records):
            raise ValueError('incomplete selected working set')
        contents = [f['content'] for f in facts]
        if not all(isinstance(s, str) and s for s in contents):
            raise ValueError('unsupported fact content')
        if sum(len(s.encode()) for s in contents) > 1024**2:
            raise ValueError('selected content exceeds preparation budget')
        text = 'Authoritative memory:\n' + '\n'.join(contents)
        framed = self.tokenizer.apply_chat_template(
            [{'role': 'system', 'content': text}], tokenize=False,
            add_generation_prompt=False, enable_thinking=False)
        tokens = self.tokenizer.encode(framed, add_special_tokens=False)
        if not 0 < len(tokens) <= self.max_memory_tokens:
            raise ValueError('selected memory exceeds certified preparation positions')
        self.load()
        ready = time.perf_counter()
        prefix = 0
        text_config = self.model.config.get_text_config()
        reusable = (len(tokens) < text_config.sliding_window
                    and not text_config.num_kv_shared_layers
                    and text_config.use_bidirectional_attention != 'all')
        if self.planner:
            plan = self.planner.plan(request['identity'], tokens)
            if not plan['same_scope']:
                self.cache = None
            if reusable and self.cache is not None:
                prefix = plan['prefix']
                # FP32 suffix evaluation exported BF16 state that failed exact
                # comparison to a fresh
                # full pass. Reuse complete identical inputs only in this mode;
                # changed content must retain the certified full-pass behavior.
                if self.compute_dtype == torch.float32 and prefix != len(tokens):
                    prefix = 0
        if prefix == len(tokens):
            cache = self.cache
        else:
            from transformers import DynamicCache
            cache = None
            if prefix:
                cache = DynamicCache(config=text_config)
                for i, layer in enumerate(self.cache.layers):
                    cache.update(layer.keys[:, :, :prefix, :].clone(),
                                 layer.values[:, :, :prefix, :].clone(), i)
            ids = torch.tensor([tokens[prefix:]])
            with torch.inference_mode():
                # Existing backbone API; the vocabulary projection is unnecessary
                # for preparation. Neither model code nor its weights are replaced.
                result = self.model.model(input_ids=ids,
                    attention_mask=torch.ones((1, len(tokens)), dtype=torch.long),
                    position_ids=torch.arange(-len(tokens) + prefix, 0).unsqueeze(0),
                    past_key_values=cache, use_cache=True)
            cache = result.past_key_values
        if self.planner:
            self.planner.plan(request['identity'], tokens, commit=True)
            self.cache = cache if reusable else None
        computed = time.perf_counter()
        banks = {i: (layer.keys.detach().to(torch.bfloat16), layer.values.detach().to(torch.bfloat16))
                 for i, layer in enumerate(cache.layers)}
        self.last_metrics = {'tokens': len(tokens), 'reused_prefix_tokens': prefix,
                             'evaluated_tokens': len(tokens) - prefix,
                             'reuse_policy': 'identical-complete-input' if self.compute_dtype == torch.float32 else 'causal-prefix',
                             'compute_dtype': str(self.compute_dtype),
                             'input_seconds': ready - started,
                             'forward_seconds': computed - ready,
                             'export_seconds': time.perf_counter() - computed}
        return tokens, banks

    def compile(self, request, output, identity, key):
        tokens, banks = self.encode(request)
        started = time.perf_counter()
        publish(Path(output), identity, key, tokens, banks)
        self.last_metrics['publish_seconds'] = time.perf_counter() - started


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--identity', required=True)
    p.add_argument('--key', required=True)
    p.add_argument('--max-memory-tokens', type=int, default=1024)
    p.add_argument('--threads', type=int, default=12)
    p.add_argument('--compute-dtype', choices=('bfloat16','float32'), default='bfloat16')
    a = p.parse_args()
    GemmaCompiler(a.model, a.max_memory_tokens, a.threads, compute_dtype=a.compute_dtype).compile(
        json.load(sys.stdin), a.output, a.identity, a.key)


if __name__ == '__main__':
    main()
