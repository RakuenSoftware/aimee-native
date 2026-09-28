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
p.add_argument('--output', required=True)
a = p.parse_args()
module = pathlib.Path(gguf_loader.__file__)
assert module.suffix == '.so', 'probe must use the installed binary'
config = SimpleNamespace(
    hf_config=AutoConfig.from_pretrained(a.model, local_files_only=True),
    model=a.model, model_weights=None, revision=None,
)
loader = gguf_loader.UnifiedGGUFLoader(LoadConfig(
    model_loader_extra_config={'gguf_weights': a.weights},
))
adapter, plan = loader._prepare_adapter(config)
names = set(get_gguf_tensor_names(plan.files.all_files))
assert names == set(plan.name_map), 'loader omitted checkpoint tensors'
assert all(plan.name_map.values()), 'missing target parameter name'
report = {
    'status': 'passed',
    'scope': 'Actual GGUF loader plan only; no model weights materialized or inference run',
    'model_type': config.hf_config.model_type,
    'adapter': type(adapter).__name__,
    'mapped_tensors': len(plan.name_map),
    'unquantized_modules': len(plan.unquantized_modules),
    'linear_layouts': len(plan.linear_layouts),
    'compiled_loader_sha256': hashlib.sha256(module.read_bytes()).hexdigest(),
}
pathlib.Path(a.output).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
