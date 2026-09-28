"""Check actual Q8 embedding lookup against independently dequantized rows."""
import json
from pathlib import Path
import gguf
import numpy as np
import torch
from vllm_gguf_plugin.quantization.vocal_embeds import _apply_gguf_embedding


def main():
    torch.set_num_threads(4)
    tensor = next(t for t in gguf.GGUFReader('/weights/gemma4-26b-q8.gguf').tensors if t.name == 'token_embd.weight')
    data = torch.from_numpy(tensor.data.copy()).cuda()
    rows = []
    for ids in ([2], [2, 105, 2364, 107, 55822, 236743, 236770], list(range(27))):
        reference = torch.from_numpy(gguf.quants.dequantize(np.ascontiguousarray(tensor.data[ids]), tensor.tensor_type)).cuda()
        for dtype in (torch.bfloat16, torch.float16):
            actual = _apply_gguf_embedding(torch.tensor(ids, device='cuda'), data, 8, 2816, dtype)
            delta = actual.float() - reference
            rows.append({'dtype': str(dtype), 'tokens': len(ids), 'finite': bool(torch.isfinite(actual).all()),
                'relative_l2': float(delta.norm() / reference.norm()),
                'max_abs_error': float(delta.abs().max()), 'actual_norm': float(actual.float().norm()),
                'reference_norm': float(reference.norm())})
    report = {'status': 'complete', 'scope': 'Q8 embedding lookup primitive only', 'cases': rows}
    Path('/evidence/result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
