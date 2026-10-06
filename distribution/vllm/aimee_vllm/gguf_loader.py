"""Explicit loader registration; never invoke upstream GGUF monkey-patch hooks.
Private model profiles use the pinned upstream GGUF adapters.
Profile availability is not model-specific release certification.
"""
from copy import copy
from pathlib import Path
from vllm.model_executor.model_loader import register_model_loader
from vllm.model_executor.layers.quantization import register_quantization_config
from vllm_gguf_plugin.loader import GGUFModelLoader,GGUFLoadPlan,_get_unquantized_modules
from vllm_gguf_plugin.quantization import GGUFConfig
from vllm_gguf_plugin.weight_utils import get_gguf_tensor_names
from vllm_gguf_plugin.weights_adapter.gemma4 import Gemma4GGUFAdapter

class UnifiedGGUFLoader(GGUFModelLoader):
    def __init__(self, load_config):
        extra=dict(load_config.model_loader_extra_config or {})
        self.weights=extra.pop('gguf_weights',None)
        expected=extra.pop('gguf_weights_sha256',None)
        if self.weights is not None and not Path(self.weights).is_absolute():
            raise ValueError('certified GGUF requires a local absolute weight path')
        if expected is not None:
            import hashlib
            if not self.weights or not isinstance(expected,str) or len(expected)!=64 or any(c not in '0123456789abcdef' for c in expected):
                raise ValueError('invalid GGUF checkpoint checksum')
            digest=hashlib.sha256()
            with Path(self.weights).open('rb') as stream:
                for block in iter(lambda:stream.read(8*1024*1024),b''):digest.update(block)
            if digest.hexdigest()!=expected:
                raise ValueError('GGUF checkpoint checksum mismatch')
        compatible=copy(load_config)
        compatible.model_loader_extra_config=extra
        super().__init__(compatible)

    def _prepare_model_files(self, model_config):
        if self.weights is not None:
            # Instance-local configuration through the supported loader interface.
            # Never replace EngineArgs methods or modify the shared model config.
            model_config=copy(model_config)
            model_config.model_weights=self.weights
        return super()._prepare_model_files(model_config)

    def _prepare_adapter(self, model_config):
        model_type=model_config.hf_config.model_type
        if model_type=='qwen3_5_text':
            adapter,plan=super()._prepare_adapter(model_config)
            if plan.files.mm_proj is not None or getattr(model_config.hf_config,'vision_config',None) is not None:
                raise RuntimeError('text-only Qwen GGUF requires a backbone without a vision projector')
            # The upstream GGUF adapter assigns the multimodal architecture to
            # text configs too. Keep its tensor/layout mapping, but instantiate
            # vLLM's registered text model for a backbone-only checkpoint.
            model_config.hf_config.architectures=['Qwen3_5ForCausalLM']
            return adapter,plan
        if model_type in ('gemma4', 'qwen3_5'):
            # Preserve upstream MoE tensor splitting and hybrid-attention weight
            # layouts. Do not apply the Unified-only name mapping to these.
            return super()._prepare_adapter(model_config)
        if model_type!='gemma4_unified':
            raise RuntimeError('unsupported private GGUF profile')
        files=self._prepare_model_files(model_config)
        adapter=Gemma4GGUFAdapter()
        names=get_gguf_tensor_names(files.all_files)
        # Gemma4Unified retains the text parameter naming consumed by this mapper.
        # Its encoder-free projections retain canonical HF names in this profile.
        # Standard converters emit this derived rotary-frequency tensor. The
        # HF/vLLM Gemma implementation computes frequencies from its config;
        # it has no weight parameter to receive it. Omit only that known tensor.
        mapping={name:(name if name.startswith('model.') else adapter.map_name(name))
                 for name in names if name!='rope_freqs.weight'}
        if any(value is None for value in mapping.values()):raise RuntimeError('unmapped GGUF tensor')
        return adapter,GGUFLoadPlan(files,mapping,_get_unquantized_modules(files,mapping),{})

def register():
    register_quantization_config('gguf')(GGUFConfig)
    register_model_loader('aimee_gguf_unified')(UnifiedGGUFLoader)
