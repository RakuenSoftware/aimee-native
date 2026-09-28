"""Isolate packaged GGUF MoE math against independently dequantized weights.

Uses actual Gemma 26B layer-zero expert weights and TP=2 geometry. Does not
patch any installed kernel or model, and does not export model weights.
"""
import json
from pathlib import Path

import gguf
import numpy as np
import torch
from vllm_gguf_plugin.quantization.fused_moe import _fused_moe_gguf
from vllm_gguf_plugin import ops


def main():
    torch.set_num_threads(4)
    torch.manual_seed(20260928)
    tensors = {t.name: t for t in gguf.GGUFReader('/weights/gemma4-26b-q8.gguf').tensors}
    gate_up = tensors['blk.0.ffn_gate_up_exps.weight'].data
    down = tensors['blk.0.ffn_down_exps.weight'].data
    intermediate = gate_up.shape[1] // 2
    # Match the rank-zero layout that the real TP=2 worker reported.
    packed13 = np.concatenate([gate_up[:, :intermediate//2],
                               gate_up[:, intermediate:intermediate+intermediate//2]], axis=1)
    packed2 = np.ascontiguousarray(down[:, :, :down.shape[2]//2])
    w13 = torch.from_numpy(packed13).cuda()
    w2 = torch.from_numpy(packed2).cuda()
    experts = [0, 3, 7, 15, 31, 63, 95, 127]
    reference = {e: (torch.from_numpy(gguf.quants.dequantize(packed13[e], gguf.GGMLQuantizationType.Q8_0)).cuda(),
                     torch.from_numpy(gguf.quants.dequantize(packed2[e], gguf.GGMLQuantizationType.Q8_0)).cuda()) for e in experts}
    rows = []
    for dtype in (torch.bfloat16, torch.float16):
        for count in (1, 7, 65):
            x = torch.randn(count, reference[0][0].shape[1], device='cuda', dtype=dtype) * .1
            ids = torch.tensor([experts] * count, device='cuda', dtype=torch.int32)
            probs = torch.softmax(torch.randn(count, len(experts), device='cuda'), dim=-1)
            actual = _fused_moe_gguf(x, w13, w2, probs, ids, 8, 8, 'gelu_pytorch_tanh')
            expected = torch.zeros_like(x, dtype=torch.float32)
            for index, expert in enumerate(experts):
                up, dn = reference[expert]
                gate, value = (x.float() @ up.T).chunk(2, dim=-1)
                activated = torch.nn.functional.gelu(gate, approximate='tanh') * value
                expected += (activated @ dn.T) * probs[:, index:index+1]
            delta = actual.float() - expected
            rows.append({'dtype': str(dtype), 'tokens': count,
                'finite': bool(torch.isfinite(actual).all()),
                'max_abs_error': float(delta.abs().max()),
                'relative_l2': float(delta.norm() / expected.norm().clamp_min(1e-12)),
                'actual_norm': float(actual.float().norm()), 'reference_norm': float(expected.norm())})
            Path('/evidence/result.json').write_text(json.dumps({'status': 'running', 'cases': rows}, indent=2) + '\n')
    report = {'status': 'complete', 'scope': 'Actual layer-zero Q8 MoE operation, TP=2 rank-zero layout; not end-to-end model validation',
        'cuda_extension_enabled': ops._CUDA_ENABLED, 'w13_shape': list(w13.shape),
        'w2_shape': list(w2.shape), 'cases': rows}
    Path('/evidence/result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
