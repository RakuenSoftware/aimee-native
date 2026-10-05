"""Lazy text-checkpoint view over local GGUF weights for native preparation."""
from collections.abc import Mapping
import re

import numpy as np
import torch
from gguf import GGUFReader, dequantize
from transformers.modeling_gguf_pytorch_utils import (
    TensorProcessor, TENSOR_PROCESSORS, get_gguf_hf_weights_map,
    load_gguf_checkpoint,
)


class GgufWeights(Mapping):
    def __init__(self, path, text_model, aliases, dtype=torch.float32):
        self.reader = GGUFReader(str(path))
        self.dtype = dtype
        self.reads = 0
        self.aliases = dict(aliases)
        architecture = ('gemma4' if text_model.config.model_type in
                        ('gemma4', 'gemma4_text', 'gemma4_unified_text') else 'qwen35')
        self.architecture = architecture
        self.config = text_model.config
        self.parsed = (load_gguf_checkpoint(str(path), return_tensors=False)
                       if architecture == 'gemma4' else {'config': self.config.to_dict()})
        self.processor = TENSOR_PROCESSORS.get(architecture, TensorProcessor)(
            config=self.parsed['config'])
        mapping = get_gguf_hf_weights_map(text_model, self.processor,
                                          model_type=architecture)
        self.tensors = {}
        for tensor in self.reader.tensors:
            target = mapping.get(tensor.name)
            if target is None and architecture == 'gemma4':
                target = self._gemma_fallback_target(tensor.name)
            if target is None and architecture == 'qwen35':
                match = re.fullmatch(r'blk\.(\d+)\.(.*)', tensor.name)
                if match:
                    suffix = {
                        'ssm_a': 'A_log',
                        'ssm_conv1d.weight': 'conv1d.weight',
                        'ssm_dt.bias': 'dt_bias',
                        'ssm_alpha.weight': 'in_proj_a.weight',
                        'ssm_beta.weight': 'in_proj_b.weight',
                        'attn_qkv.weight': 'in_proj_qkv.weight',
                        'attn_gate.weight': 'in_proj_z.weight',
                        'ssm_norm.weight': 'norm.weight',
                        'ssm_out.weight': 'out_proj.weight',
                    }.get(match[2])
                    if suffix:
                        target = f'layers.{match[1]}.linear_attn.{suffix}'
            if target is not None:
                self.tensors['model.language_model.' + target] = tensor
        self.expected_shapes = {'model.language_model.' + name: tuple(value.shape)
                                for name, value in text_model.state_dict().items()}
        missing = self.expected_shapes.keys() - self.tensors.keys()
        if missing:
            raise ValueError('GGUF checkpoint is missing text tensors: ' + repr(sorted(missing)[:8]))
        if any(name not in self.tensors for name in self.aliases.values()):
            raise ValueError('GGUF aliases do not match text tensors')

    def __iter__(self):
        yield from self.tensors
        yield from self.aliases

    def __len__(self):
        return len(self.tensors) + len(self.aliases)

    def __getitem__(self, name):
        canonical = self.aliases.get(name, name)
        tensor = self.tensors[canonical]
        weights = dequantize(tensor.data, tensor.tensor_type)
        result = self.processor.process(weights, tensor.name,
                                        tensor_key_mapping={}, parsed_parameters=self.parsed)
        if result.name not in (None, tensor.name):
            raise ValueError('GGUF tensor mapping changed during preparation')
        array = self._qwen_restore(canonical, result.weights) if self.architecture == 'qwen35' else result.weights
        if tuple(array.shape) != self.expected_shapes[canonical]:
            raise ValueError('GGUF text tensor has wrong shape: ' + canonical)
        value = torch.from_numpy(array.copy())
        self.reads += 1
        return value.to(self.dtype) if value.is_floating_point() else value

    def close(self):
        self.tensors.clear()
        self.reader = None

    @staticmethod
    def _gemma_fallback_target(name):
        match = re.fullmatch(r'blk\.(\d+)\.(.*)', name)
        if not match:
            return None
        suffix = {
            'layer_output_scale.weight': 'layer_scalar',
            'ffn_down_exps.weight': 'experts.down_proj',
            'ffn_gate_up_exps.weight': 'experts.gate_up_proj',
            'post_ffw_norm_1.weight': 'post_feedforward_layernorm_1.weight',
            'post_ffw_norm_2.weight': 'post_feedforward_layernorm_2.weight',
            'pre_ffw_norm_2.weight': 'pre_feedforward_layernorm_2.weight',
            'ffn_down_exps.scale': 'router.per_expert_scale',
            'ffn_gate_inp.weight': 'router.proj.weight',
            'ffn_gate_inp.scale': 'router.scale',
        }.get(match[2])
        return f'layers.{match[1]}.{suffix}' if suffix else None

    def _untile(self, values, dimension, head_dim):
        keys = self.config.linear_num_key_heads
        ratio = self.config.linear_num_value_heads // keys
        shape = list(values.shape)
        shape[dimension:dimension + 1] = [ratio, keys, head_dim]
        return values.reshape(shape).swapaxes(dimension, dimension + 1).reshape(values.shape)

    def _qwen_restore(self, name, values):
        # GGUF stores the effective scale for Qwen's zero-centered RMSNorm,
        # while the Transformers implementation applies (1 + weight). Undo
        # the GGUF conversion before the independent preparation pass. The
        # gated-delta SSM norm is not zero-centered and must stay unchanged.
        if (name.endswith(('.input_layernorm.weight',
                           '.post_attention_layernorm.weight',
                           '.self_attn.q_norm.weight',
                           '.self_attn.k_norm.weight'))
                or name == 'model.language_model.norm.weight'):
            return values - 1.0
        if self.config.linear_num_key_heads == self.config.linear_num_value_heads:
            if name.endswith('.linear_attn.A_log'):
                return np.log(-values)
            if name.endswith('.linear_attn.conv1d.weight'):
                return values.squeeze()[:, None, :]
            return values
        if name.endswith('.linear_attn.in_proj_qkv.weight'):
            qdim = self.config.linear_key_head_dim * self.config.linear_num_key_heads
            return np.concatenate((values[:2 * qdim],
                self._untile(values[2 * qdim:], 0, self.config.linear_value_head_dim)), axis=0)
        if name.endswith('.linear_attn.conv1d.weight'):
            values = values.squeeze()
            qk = self.config.linear_key_head_dim * self.config.linear_num_key_heads * 2
            restored = np.concatenate((values[:qk],
                self._untile(values[qk:], 0, self.config.linear_value_head_dim)), axis=0)
            return restored[:, None, :]
        if name.endswith('.linear_attn.out_proj.weight'):
            return self._untile(values, 1, self.config.linear_value_head_dim)
        if name.endswith(('.linear_attn.in_proj_a.weight', '.linear_attn.in_proj_b.weight')):
            return self._untile(values, 0, 1)
        if name.endswith(('.linear_attn.in_proj_z.weight',)):
            return self._untile(values, 0, self.config.linear_value_head_dim)
        if name.endswith(('.linear_attn.A_log', '.linear_attn.dt_bias')):
            values = self._untile(values, 0, 1)
            return np.log(-values) if name.endswith('.A_log') else values
        return values
