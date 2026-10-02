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
        if self.weights is not None and not Path(self.weights).is_absolute():
            raise ValueError('certified GGUF requires a local absolute weight path')
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
        mapping={name:(name if name.startswith('model.') else adapter.map_name(name)) for name in names}
        if any(value is None for value in mapping.values()):raise RuntimeError('unmapped GGUF tensor')
        return adapter,GGUFLoadPlan(files,mapping,_get_unquantized_modules(files,mapping),{})

def register():
    register_quantization_config('gguf')(GGUFConfig)
    register_model_loader('aimee_gguf_unified')(UnifiedGGUFLoader)
