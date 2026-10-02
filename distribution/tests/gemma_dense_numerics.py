"""Actual Gemma Q8 dense/vocabulary operations against dequantized reference."""
import json
from pathlib import Path
import gguf
import numpy as np
import torch
from vllm_gguf_plugin.quantization.linear import _fused_mul_mat_gguf
from gemma_loaded_q8_parity import expected


def main():
    torch.set_num_threads(4)
    torch.manual_seed(20260928)
    tensors = {t.name: t.data for t in gguf.GGUFReader('/weights/gemma4-26b-q8.gguf').tensors}
    names = [f'language_model.model.layers.{layer}.{suffix}' for layer in (0, 5)
             for suffix in ('self_attn.qkv_proj.weight', 'self_attn.o_proj.weight',
                            'mlp.gate_up_proj.weight', 'mlp.down_proj.weight')]
    names += ['language_model.model.embed_tokens.weight']
    rows = []
    for name in names:
        packed = np.ascontiguousarray(expected(tensors, name, 0))
        weight = torch.from_numpy(packed).cuda()
        reference = torch.from_numpy(gguf.quants.dequantize(packed, gguf.GGMLQuantizationType.Q8_0)).cuda()
        for dtype in (torch.bfloat16, torch.float16):
            for count in (1, 27):
                for scale in (.1, 10.):
                    x = torch.randn(count, reference.shape[1], device='cuda', dtype=dtype) * scale
                    actual = _fused_mul_mat_gguf(x, weight, 8)
                    ref = x.float() @ reference.T
                    delta = actual.float() - ref
                    rows.append({'name': name, 'shape': list(reference.shape),
                        'dtype': str(dtype), 'tokens': count, 'input_scale': scale,
                        'finite': bool(torch.isfinite(actual).all()),
                        'max_abs_error': float(delta.abs().max()),
                        'relative_l2': float(delta.norm() / ref.norm().clamp_min(1e-12)),
                        'actual_norm': float(actual.float().norm()), 'reference_norm': float(ref.norm())})
                    Path('/evidence/result.json').write_text(json.dumps({'status': 'running', 'cases': rows}, indent=2) + '\n')
        del weight, reference, packed
    report = {'status': 'complete', 'scope': 'Sampled Gemma dense and vocabulary Q8 operations, rank-zero TP=2 layout; no model-quality claim', 'cases': rows}
    Path('/evidence/result.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
