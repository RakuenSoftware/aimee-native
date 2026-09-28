"""Read the actual GGUF through the installed compiled loader, without GPUs."""
import argparse
import hashlib
import json
import pathlib
from types import SimpleNamespace

from transformers import AutoConfig
from vllm.config import LoadConfig
from aimee_vllm import gguf_loader
from vllm_gguf_plugin.weight_utils import get_gguf_tensor_names


p = argparse.ArgumentParser()
p.add_argument('--model', required=True)
p.add_argument('--weights', required=True)
p.add_argument('--mmproj')
p.add_argument('--allow-unused-mtp', action='store_true',
               help='Qwen only: permit the complete optional single draft block, retained in GGUF')
p.add_argument('--output', required=True)
a = p.parse_args()
module = pathlib.Path(gguf_loader.__file__)
assert module.suffix == '.so', 'probe must use the installed binary'
config = SimpleNamespace(
    hf_config=AutoConfig.from_pretrained(a.model, local_files_only=True),
    model=a.model, model_weights=None, revision=None,
)
extra = {'gguf_weights': a.weights}
if a.mmproj:
    extra['mm_proj'] = a.mmproj
loader = gguf_loader.UnifiedGGUFLoader(LoadConfig(model_loader_extra_config=extra))
adapter, plan = loader._prepare_adapter(config)
names = set(get_gguf_tensor_names(plan.files.all_files))
missing = sorted(names - set(plan.name_map))
ignored = []
if missing and a.allow_unused_mtp:
    text = config.hf_config.get_text_config()
    assert config.hf_config.model_type == 'qwen3_5'
    assert text.num_hidden_layers == 64 and text.mtp_num_hidden_layers == 1
    prefix = 'blk.64.'
    draft = {prefix + suffix for suffix in (
        'attn_k.weight', 'attn_k_norm.weight', 'attn_norm.weight',
        'attn_output.weight', 'attn_q.weight', 'attn_q_norm.weight', 'attn_v.weight',
        'ffn_down.weight', 'ffn_gate.weight', 'ffn_up.weight',
        'nextn.eh_proj.weight', 'nextn.enorm.weight', 'nextn.hnorm.weight',
        'nextn.shared_head_norm.weight', 'post_attention_norm.weight')}
    if set(missing) == draft:
        ignored = missing
if missing and not ignored:
    pathlib.Path(a.output).write_text(json.dumps({
        'status': 'failed', 'scope': 'Actual GGUF loading plan omits tensors; inspect before GPU load',
        'unmapped_tensors': missing, 'mapped_tensors': len(plan.name_map),
        'checkpoint_tensors': len(names),
    }, indent=2) + '\n')
    raise AssertionError('loader omitted checkpoint tensors')
assert set(plan.name_map) | set(ignored) == names, 'loader invents checkpoint tensors'
assert all(plan.name_map.values()), 'missing target parameter name'
report = {
    'status': 'passed',
    'scope': 'Actual GGUF loader plan only; no model weights materialized or inference run',
    'model_type': config.hf_config.model_type,
    'adapter': type(adapter).__name__,
    'mapped_tensors': len(plan.name_map),
    'checkpoint_tensors': len(names),
    'unused_speculative_draft_tensors': ignored,
    'unquantized_modules': len(plan.unquantized_modules),
    'linear_layouts': len(plan.linear_layouts),
    'compiled_loader_sha256': hashlib.sha256(module.read_bytes()).hexdigest(),
}
pathlib.Path(a.output).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
