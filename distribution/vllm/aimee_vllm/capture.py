"""Offline, single-request prefix capture; disabled in deployed HTTP workers.

Observe the unmodified model's post-RoPE attention tensors and private GDN
cache after each prefill chunk. Sampling happens after the captured boundary.
"""
import hashlib
import json
from pathlib import Path
import torch
from .precision import runtime_profile, model_identity

from .capture_session import CaptureSession, raw_tensor



class PrefixCapture(CaptureSession):
    def __init__(self, config, runner, tokens, context, destination):
        if config.get('quantization')!='fp8':
            raise RuntimeError('engine capture currently supports only FP8')
        if config.get('offline_prefix_capture') is not True:
            raise RuntimeError('prefix capture requires an offline worker')
        if config.get('serve', {}).get('tensor_parallel_size', 1) != 1:
            raise RuntimeError('prefix capture currently requires one GPU')
        if not tokens or len(tokens) > config.get('serve', {}).get('max_model_len', 2048):
            raise ValueError('prefix token budget exceeded')
        from tokenizers import Tokenizer
        tokenizer = Tokenizer.from_file(str(Path(config['model'])/'tokenizer.json'))
        text = tokenizer.decode(tokens, skip_special_tokens=False)
        from .model_adapter import ModelAdapter
        ModelAdapter(config).call('validate_prefix_text',text=text,context=context)
        self.config, self.runner = config, runner
        self.tokens, self.context = list(tokens), context
        self.destination = Path(destination)
        if self.destination.exists():
            raise ValueError('capture destination must be new')
        self.attention, self.recurrent, self.hooks = {}, {}, []
        self.request = None
        c = json.loads((Path(config['model'])/'config.json').read_bytes())
        self.architecture = c.get('text_config', c)
        from vllm.model_executor.layers.mamba.gdn.qwen_gdn_linear_attn import QwenGatedDeltaNetAttention
        from vllm.model_executor.layers.mamba.mamba_utils import is_conv_state_dim_first
        from vllm.forward_context import get_forward_context
        import re
        for _, module in runner.model.named_modules():
            if not isinstance(module, QwenGatedDeltaNetAttention):
                continue
            match = re.search(r'(?:^|\.)layers\.(\d+)\.', module.prefix)
            if match is None:
                raise RuntimeError('capture recurrent layer identity unavailable')
            layer = int(match.group(1))
            def after(module, args, output, layer=layer):
                metadata = get_forward_context().attn_metadata
                metadata = metadata.get(module.prefix) if isinstance(metadata, dict) else None
                if metadata is None:return
                slots = metadata.non_spec_state_indices_tensor.tolist()
                if len(slots) != 1 or runner.input_batch.req_ids != [self.request]:
                    raise RuntimeError('capture requires an exclusive request')
                conv, rnn = (t[slots[0]].detach().cpu().clone() for t in module.kv_cache)
                if not is_conv_state_dim_first():conv = conv.transpose(-1, -2)
                # The runtime retains K-1 convolution columns. The canonical
                # storage includes a discarded leading column, never consumed.
                conv = torch.cat((torch.zeros_like(conv[:, :1]), conv), dim=-1).unsqueeze(0)
                rnn = rnn.transpose(-1, -2).contiguous().unsqueeze(0)
                self.recurrent[layer] = (conv, rnn)
            self.hooks.append(module.register_forward_hook(after))

    def finish(self):
        c = self.architecture
        full = {i for i, kind in enumerate(c['layer_types']) if kind == 'full_attention'}
        linear = {i for i, kind in enumerate(c['layer_types']) if kind == 'linear_attention'}
        if set(self.attention) != full or set(self.recurrent) != linear:
            raise RuntimeError('incomplete captured layer coverage')
        data = bytearray();segments = []
        for layer in sorted(full):
            for value, chunks in enumerate(self.attention[layer]):
                tensor = torch.cat(chunks)
                if list(tensor.shape) != [len(self.tokens), c['num_key_value_heads'], c['head_dim']]:
                    raise RuntimeError('incomplete captured attention geometry')
                tensor = tensor.transpose(0, 1).contiguous()
                data.extend(raw_tensor(tensor))
                segments.append({'layer': layer, 'value': bool(value), 'heads': c['num_key_value_heads'],
                                 'width': c['head_dim'], 'positions': len(self.tokens)})
        recurrent = bytearray();layouts = []
        for layer in sorted(linear):
            for part, tensor in zip(('conv', 'recurrent'), self.recurrent[layer]):
                dtype = 'bf16' if tensor.dtype == torch.bfloat16 else 'f32'
                raw = raw_tensor(tensor)
                layouts.append({'layer': layer, 'part': part, 'dtype': dtype, 'shape': list(tensor.shape),
                                'offset': len(recurrent), 'bytes': len(raw)})
                recurrent.extend(raw)
        digest = lambda raw: hashlib.sha256(raw).hexdigest()
        root = Path(self.config['model']);config = (root/'config.json').read_bytes();tokenizer = (root/'tokenizer.json').read_bytes()
        profile = runtime_profile(self.config)
        model = model_identity(config, tokenizer, self.config['model_revision'], profile)
        key = digest(b'engine-prefix-v1\0'+model.encode()+json.dumps(self.tokens).encode())
        offset = (4096+len(data)+4095)&~4095
        index = {'version': 1, 'model': model, 'schema': {'segments': segments,
                 'row_bytes': sum(s['heads']*s['width']*2 for s in segments)},
                 'prototypes': len(self.tokens), 'dictionary_bytes': len(data), 'dictionary_sha256': digest(data),
                 'records': {key: {'offset': offset, 'tokens': self.tokens}},
                 'experimental_approximation': False, 'head_major': False, 'native_layout': True}
        encode = lambda value: (json.dumps(value, sort_keys=True)+'\n').encode()
        index_raw = encode(index);rnn_digest = digest(recurrent)
        spec = {'schema': 1, 'model': model, 'key': key, 'architecture': c,
                'positioning': 'native-prefix-absolute-v1', 'attention_index_sha256': digest(index_raw),
                'model_config_sha256': digest(config), 'model_revision': self.config['model_revision'],
                'tokenizer_sha256': digest(tokenizer), 'encoder_weight_profile': 'vllm-fp8' if profile else 'bf16',
                'runtime_profile': profile, 'encoding': 'system-message',
                'system_context_sha256': digest(self.context.strip().encode()),
                'recurrent': {'version': 1, 'bytes': len(recurrent), 'sha256': rnn_digest,
                              'payload': rnn_digest+'.rnn.bin', 'layouts': layouts}}
        from os import open as os_open, fdopen, O_WRONLY, O_CREAT, O_EXCL, fsync
        self.destination.mkdir(mode=0o700)
        def write(name, raw):
            with fdopen(os_open(self.destination/name, O_WRONLY|O_CREAT|O_EXCL, 0o600), 'wb') as f:
                f.write(raw);f.flush();fsync(f.fileno())
        write('compact.pack', b'\0'*4096+data+b'\0'*(offset-4096-len(data))+
              b''.join(i.to_bytes(4, 'little') for i in range(len(self.tokens))))
        write('index.json', index_raw);write(rnn_digest+'.rnn.bin', recurrent)
        manifest = encode(spec);write('hybrid.json', manifest)
        return {'root': str(self.destination), 'model': model, 'key': key, 'hybrid_state': digest(manifest)}
