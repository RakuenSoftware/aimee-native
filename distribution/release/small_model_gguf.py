"""Dedicated dense Gemma 4 weight mapping, including per-layer inputs."""
from aimee_native_runtime.gguf_loader import UnifiedGGUFLoader
from vllm_gguf_plugin.loader import GGUFLoadPlan, _get_unquantized_modules
from vllm_gguf_plugin.weight_utils import get_gguf_tensor_names
from vllm_gguf_plugin.weights_adapter.gemma4 import Gemma4GGUFAdapter

ROOT_NAMES = {
    'per_layer_model_proj.weight': 'model.language_model.per_layer_model_projection.weight',
    'per_layer_proj_norm.weight': 'model.language_model.per_layer_projection_norm.weight',
    'per_layer_token_embd.weight': 'model.language_model.embed_tokens_per_layer.weight',
}
LAYER_NAMES = {
    'inp_gate.weight': 'per_layer_input_gate.weight',
    'proj.weight': 'per_layer_projection.weight',
    'post_norm.weight': 'post_per_layer_input_norm.weight',
}


def map_name(name):
    if name in ROOT_NAMES:
        return ROOT_NAMES[name]
    parts = name.split('.', 2)
    if len(parts) == 3 and parts[0] == 'blk' and parts[1].isdigit() and parts[2] in LAYER_NAMES:
        return 'model.language_model.layers.' + parts[1] + '.' + LAYER_NAMES[parts[2]]
    return Gemma4GGUFAdapter.map_name(name)


class SmallGemmaWeightsAdapter(Gemma4GGUFAdapter):
    def transform_weights(self, weights, model_config):
        # These two small-model projections use vLLM ReplicatedLinear, whose
        # loader cannot receive lazy packed GGUF parameters. Materialize only
        # these small matrices; leave embeddings and all other weights packed.
        import torch
        from gguf import GGMLQuantizationType
        from gguf.quants import dequantize
        pending = {}
        for name, weight in super().transform_weights(weights, model_config):
            if '.per_layer_input_gate.' not in name and '.per_layer_projection.' not in name:
                yield name, weight
                continue
            if name.endswith('.weight_type'):
                target = name.removesuffix('_type')
                if target in pending:
                    raise RuntimeError('duplicate small Gemma projection quantization type')
                pending[target] = GGMLQuantizationType(int(weight.item()))
                continue
            if name in pending:
                kind = pending.pop(name)
                weight = torch.from_numpy(dequantize(weight.numpy(), kind)).to(torch.bfloat16)
            elif not weight.is_floating_point():
                raise RuntimeError('missing small Gemma projection quantization type')
            yield name, weight
        if pending:
            raise RuntimeError('missing small Gemma projection weights')


class SmallGemmaGGUFLoader(UnifiedGGUFLoader):
    def _prepare_adapter(self, model_config):
        config = model_config.hf_config
        text = config.get_text_config()
        if config.model_type != 'gemma4' or text.num_hidden_layers not in (35, 42) or text.hidden_size_per_layer_input != 256:
            raise RuntimeError('wrong dedicated small Gemma GGUF profile')
        files = self._prepare_model_files(model_config)
        names = get_gguf_tensor_names(files.all_files)
        # Rotary frequencies are derived from the validated HF configuration.
        mapping = {name: map_name(name) for name in names if name != 'rope_freqs.weight'}
        if any(target is None for target in mapping.values()):
            raise RuntimeError('unmapped small Gemma GGUF tensor')
        if len(set(mapping.values())) != len(mapping):
            raise RuntimeError('duplicate small Gemma GGUF destination')
        if not set(ROOT_NAMES).issubset(mapping):
            raise RuntimeError('missing small Gemma per-layer embedding weights')
        projections = tuple(target.removesuffix('.weight') for target in mapping.values()
                            if '.per_layer_input_gate.' in target or '.per_layer_projection.' in target)
        return SmallGemmaWeightsAdapter(), GGUFLoadPlan(
            files, mapping, _get_unquantized_modules(files, mapping) + projections, {})


def register():
    from vllm.model_executor.model_loader import register_model_loader
    from vllm.model_executor.layers.quantization import register_quantization_config
    from vllm_gguf_plugin.quantization import GGUFConfig
    register_quantization_config('gguf')(GGUFConfig)
    register_model_loader('aimee_gguf_unified')(SmallGemmaGGUFLoader)
