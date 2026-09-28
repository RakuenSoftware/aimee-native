"""CPU-only dispatch probe against pinned vLLM; does not certify model loading."""
import argparse
import importlib.util
import json
from types import SimpleNamespace
from unittest.mock import patch
from vllm_gguf_plugin.loader import GGUFModelLoader
from vllm_gguf_plugin.weights_adapter import get_weights_adapter

p=argparse.ArgumentParser();p.add_argument('--source',required=True);a=p.parse_args()
spec=importlib.util.spec_from_file_location('candidate_gguf_loader',a.source)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
loader=object.__new__(module.UnifiedGGUFLoader)
rows=[]
for kind in ['gemma4','qwen3_5']:
    config=SimpleNamespace(hf_config=SimpleNamespace(model_type=kind))
    adapter=get_weights_adapter(config.hf_config)
    sentinel=object()
    with patch.object(GGUFModelLoader,'_prepare_adapter',return_value=sentinel) as upstream:
        assert loader._prepare_adapter(config) is sentinel
        upstream.assert_called_once_with(config)
    rows.append({'architecture':kind,'upstream_adapter':type(adapter).__name__,'delegation':'passed'})
try:loader._prepare_adapter(SimpleNamespace(hf_config=SimpleNamespace(model_type='unknown')))
except RuntimeError:pass
else:raise AssertionError('unknown architecture accepted')
print(json.dumps({'status':'passed','rows':rows,'scope':'Pinned upstream adapter availability and private dispatch only; no weights loaded, no GPU execution, no model accuracy claim'},indent=2))
