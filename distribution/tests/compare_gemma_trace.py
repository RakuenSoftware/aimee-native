"""Derive comparison metrics from private CPU and GPU activation traces."""
import json
import math
from pathlib import Path
import sys


def main():
    root = Path(sys.argv[1])
    output = root / 'comparison.json'
    assert not output.exists(), 'preserve earlier comparison'
    cpu = json.loads((root / 'cpu-trace.json').read_text())
    gpu = json.loads((root / 'gpu-trace.json').read_text())
    assert cpu['input_token_ids'] == gpu['input_token_ids'], 'different input sequences'
    names = ['embedding', *('layer.' + str(i) for i in range(30)), 'norm']
    assert set(cpu['trace']) == set(names)
    rows = []
    for worker in gpu['workers']:
        assert set(worker['trace']) == set(names)
        for name in names:
            a, b = cpu['trace'][name], worker['trace'][name]
            assert len(a) == len(b) == 2816
            an = math.sqrt(sum(x*x for x in a))
            bn = math.sqrt(sum(x*x for x in b))
            rows.append({'rank': worker['rank'], 'layer': name,
                'finite': all(math.isfinite(x) for x in a + b),
                'cpu_norm': an, 'gpu_norm': bn,
                'cosine_similarity': sum(x*y for x,y in zip(a,b)) / max(an*bn, 1e-30),
                'relative_l2': math.sqrt(sum((x-y)**2 for x,y in zip(a,b))) / max(an, 1e-30)})
    output.write_text(json.dumps({'scope': 'First-prefill last-token activation comparison: original FP32 CPU vs packaged Q8/BF16 GPU; same prompt, no native memory',
        'input_tokens': len(cpu['input_token_ids']), 'gpu_answer': gpu['answer'],
        'gpu_token_ids': gpu['token_ids'], 'rows': rows}, indent=2) + '\n')
    print(json.dumps(rows))


if __name__ == '__main__':
    main()
