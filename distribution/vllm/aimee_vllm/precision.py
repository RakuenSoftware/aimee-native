"""Exact serving arithmetic identity for engine-produced native prefixes."""
import hashlib
import importlib.metadata
import json


def runtime_profile(config):
    quantization = config.get('quantization')
    if quantization is None:
        return None  # Preserve the existing immutable BF16 encoder contract.
    if quantization != 'fp8' or config.get('gguf_weights'):
        raise ValueError('supported serving quantization is fp8 without GGUF')
    return {
        'schema': 1, 'producer': 'vllm', 'quantization': 'fp8',
        'device_capability': [12,0], 'activation_scheme': 'dynamic', 'attention_dtype': 'bf16',
        'conv_dtype': 'bf16', 'recurrent_dtype': 'f32',
        'attention_backend': 'aimee-triton-v1',
        'gdn_prefill_backend': config.get('serve', {}).get('gdn_prefill_backend', 'triton'),
        'versions': {name: importlib.metadata.version(name)
                     for name in ('vllm', 'torch', 'triton')},
    }


def model_identity(config_bytes, tokenizer_bytes, revision, profile):
    if profile is None:
        payload = b'aimee-complete-hybrid-v1' + revision.encode() + b'\0'
    else:
        payload = (b'aimee-engine-hybrid-v2' + revision.encode() + b'\0' +
                   json.dumps(profile, sort_keys=True, separators=(',', ':')).encode() + b'\0')
    return hashlib.sha256(payload + config_bytes + tokenizer_bytes).hexdigest()
