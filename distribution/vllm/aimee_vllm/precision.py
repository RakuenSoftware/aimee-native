"""Exact serving arithmetic identity for engine-produced native prefixes."""
import hashlib
import importlib.metadata
import json


def runtime_profile(config):
    quantization = config.get('quantization')
    if config.get('gguf_weights'):
        digest = config.get('gguf_weights_sha256', '')
        if (quantization is not None or config.get('gguf_weight_profile') != 'Q4_K_M'
            or not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)
            or config.get('gguf_matrix_backend', 'triton') != 'triton'):
            raise ValueError('hybrid GGUF capture requires a bound Q4_K_M Triton checkpoint')
        import torch
        return {
            'schema': 1, 'producer': 'vllm', 'quantization': 'gguf',
            'weights_sha256': digest, 'weight_profile': 'Q4_K_M',
            'device_capability': list(torch.cuda.get_device_capability()),
            'attention_dtype': 'bf16', 'conv_dtype': 'bf16', 'recurrent_dtype': 'f32',
            'attention_backend': 'aimee-triton-v1', 'gguf_matrix_backend': 'triton',
            'gdn_prefill_backend': config.get('serve', {}).get('gdn_prefill_backend', 'triton'),
            'versions': {name: importlib.metadata.version(name)
                         for name in ('vllm', 'torch', 'triton', 'vllm-gguf-plugin')},
        }
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


def encoder_weight_profile(profile):
    if profile is None:
        return 'bf16'
    return 'vllm-gguf-Q4_K_M' if profile['quantization'] == 'gguf' else 'vllm-fp8'
