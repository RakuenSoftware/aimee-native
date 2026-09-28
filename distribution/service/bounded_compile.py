"""Private FP32 preparation for larger Gemma/Qwen checkpoints.

Uses original Transformers models with supported Accelerate offload hooks.
No prepared tensors are served from this process; publication uses the existing
Rust-backed format. Keep this module out of client distribution images.
"""
import json
from pathlib import Path
import time

import torch
from accelerate import cpu_offload, init_empty_weights
from transformers import AutoConfig, AutoTokenizer, Gemma4TextModel, Qwen3_5TextModel
from checkpoint_weights import CheckpointWeights
from gemma_compile import GemmaCompiler


class BoundedTextCompiler(GemmaCompiler):
    def __init__(self, model, max_memory_tokens=1024, threads=12, reuse_library=None,
                 compute_dtype='float32'):
        if compute_dtype != 'float32':
            raise ValueError('bounded preparation requires FP32 compute')
        if reuse_library is not None:
            raise ValueError('bounded preparation currently performs full passes without prefix reuse')
        torch.set_num_threads(threads)
        self.model_path = model
        self.max_memory_tokens = max_memory_tokens
        self.compute_dtype = torch.float32
        self.tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
        self.config = AutoConfig.from_pretrained(model, local_files_only=True)
        if self.config.model_type not in ('gemma4', 'qwen3_5'):
            raise ValueError('unsupported bounded preparation architecture')
        self.model = None
        self.weights = None
        self.last_metrics = {}

    def load(self):
        if self.model is not None:
            return
        text = self.config.get_text_config()
        text._attn_implementation = 'eager'
        cls = Gemma4TextModel if self.config.model_type == 'gemma4' else Qwen3_5TextModel
        with init_empty_weights():
            model = cls(text).eval()
        index = json.loads((Path(self.model_path) / 'model.safetensors.index.json').read_text())['weight_map']
        aliases = {name: 'model.language_model.' + name for name in model.state_dict()}
        absent = [name for name, canonical in aliases.items() if canonical not in index]
        if absent:
            raise ValueError('checkpoint missing text-model tensors: ' + repr(absent))
        weights = CheckpointWeights(self.model_path, aliases=aliases)
        try:
            cpu_offload(model, execution_device=torch.device('cpu'), state_dict=weights,
                preload_module_classes=['Qwen3_5GatedDeltaNet'] if self.config.model_type == 'qwen3_5' else [])
        except BaseException:
            weights.close()
            raise
        self.model = model
        self.weights = weights

    def encode(self, request):
        started = time.perf_counter()
        facts = request['response']['facts']
        records = request['identity']['records']
        if not facts or len(facts) != len(records):
            raise ValueError('incomplete selected working set')
        contents = [fact['content'] for fact in facts]
        if not all(isinstance(s, str) and s for s in contents):
            raise ValueError('unsupported fact content')
        if sum(len(s.encode()) for s in contents) > 1024**2:
            raise ValueError('selected content exceeds preparation budget')
        framed = self.tokenizer.apply_chat_template(
            [{'role': 'system', 'content': 'Authoritative memory:\n' + '\n'.join(contents)}],
            tokenize=False, add_generation_prompt=False, enable_thinking=False)
        tokens = self.tokenizer.encode(framed, add_special_tokens=False)
        if not 0 < len(tokens) <= self.max_memory_tokens:
            raise ValueError('selected memory exceeds preparation positions')
        self.load()
        ready = time.perf_counter()
        count = len(tokens)
        positions = torch.arange(-count, 0) if self.config.model_type == 'gemma4' else torch.arange(count)
        reads = self.weights.reads
        with torch.inference_mode():
            result = self.model(input_ids=torch.tensor([tokens]),
                attention_mask=torch.ones((1, count), dtype=torch.long),
                position_ids=positions.unsqueeze(0), use_cache=True)
        computed = time.perf_counter()
        types = self.config.get_text_config().layer_types
        expected = {i for i, kind in enumerate(types) if kind in ('full_attention', 'sliding_attention')}
        banks = {}
        for i in sorted(expected):
            layer = result.past_key_values.layers[i]
            keys, values = layer.keys, layer.values
            if keys is None or values is None or keys.shape[-2] != count or values.shape[-2] != count:
                raise ValueError('cache did not retain every selected memory position')
            if not torch.isfinite(keys).all() or not torch.isfinite(values).all():
                raise ValueError('nonfinite prepared native state')
            banks[i] = (keys.detach().to(torch.bfloat16), values.detach().to(torch.bfloat16))
        if not banks:
            raise ValueError('no supported attention layers')
        self.last_metrics = {
            'tokens': count, 'reused_prefix_tokens': 0, 'evaluated_tokens': count,
            'reuse_policy': 'full-pass', 'compute_dtype': str(self.compute_dtype),
            'weight_policy': 'checkpoint-on-demand', 'weight_reads': self.weights.reads - reads,
            'input_seconds': ready - started, 'forward_seconds': computed - ready,
            'export_seconds': time.perf_counter() - computed,
        }
        return tokens, banks

    def close(self):
        if self.weights is not None:
            self.weights.close()
        self.model = None
        self.weights = None
