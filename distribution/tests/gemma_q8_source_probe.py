"""Check sampled real GGUF payloads against the original checkpoint on CPU."""
import json
from pathlib import Path
import sys

sys.path.insert(0, '/opt/aimee-memory-lab/qwen27-release-20260928/converter/gguf-py')
import gguf
import numpy as np
from safetensors import safe_open
import torch


def main():
    torch.set_num_threads(2)
    root = Path('/opt/aimee-memory-lab/gemma4-moe')
    index = json.loads((root / 'model.safetensors.index.json').read_text())['weight_map']
    tensors = {t.name: t for t in gguf.GGUFReader('/opt/aimee-memory-lab/gemma26-release-20260928/gemma4-26b-q8.gguf').tensors}
    mapping = {'self_attn.q_proj.weight': 'attn_q.weight', 'self_attn.k_proj.weight': 'attn_k.weight',
        'self_attn.v_proj.weight': 'attn_v.weight', 'self_attn.o_proj.weight': 'attn_output.weight',
        'mlp.gate_proj.weight': 'ffn_gate.weight', 'mlp.up_proj.weight': 'ffn_up.weight',
        'mlp.down_proj.weight': 'ffn_down.weight',
        'experts.gate_up_proj': 'ffn_gate_up_exps.weight', 'experts.down_proj': 'ffn_down_exps.weight'}
    rows = []
    absent_source_projections = []
    for layer in (0, 5, 29):
        for suffix, target in mapping.items():
            source = f'model.language_model.layers.{layer}.{suffix}'
            if source not in index:
                assert f'blk.{layer}.{target}' not in tensors
                absent_source_projections.append(source)
                continue
            tensor = tensors[f'blk.{layer}.{target}']
            with safe_open(root / index[source], framework='pt', device='cpu') as f:
                view = f.get_slice(source)
                selectors = [(slice(0, 8), slice(None)), (slice(-8, None), slice(None))]
                if len(view.get_shape()) == 3:
                    selectors = [(e, *s) for e in (0, 127) for s in selectors]
                for selection in selectors:
                    original = view[selection].float().numpy()
                    restored = gguf.quants.dequantize(np.ascontiguousarray(tensor.data[selection]), tensor.tensor_type)
                    assert restored.shape == original.shape
                    relative = float(np.linalg.norm(restored - original) / max(np.linalg.norm(original), 1e-20))
                    rows.append({'source': source, 'selection': str(selection),
                        'finite': bool(np.isfinite(restored).all()), 'relative_l2': relative,
                        'max_abs_error': float(np.max(np.abs(restored - original)))})
    report = {'scope': 'CPU sampled Q8 payload versus original checkpoint; no serving-kernel correctness claim',
        'cases': rows, 'absent_source_projections': absent_source_projections,
        'all_below_two_percent_relative_l2': all(r['finite'] and r['relative_l2'] < .02 for r in rows)}
    Path(sys.argv[1]).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'cases': len(rows), 'all_below_two_percent_relative_l2': report['all_below_two_percent_relative_l2'],
                      'maximum_relative_l2': max(r['relative_l2'] for r in rows)}))


if __name__ == '__main__':
    main()
