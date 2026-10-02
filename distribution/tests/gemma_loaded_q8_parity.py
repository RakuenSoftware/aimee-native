"""Compare loaded TP=2 quantized bytes to independently sliced GGUF payloads."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, '/opt/aimee-memory-lab/qwen27-release-20260928/converter/gguf-py')
import gguf
import numpy as np


def expected(tensors, name, rank):
    def rows(value):
        half = value.shape[0] // 2
        return value[rank*half:(rank+1)*half]
    def columns(value):
        half = value.shape[-1] // 2
        return value[..., rank*half:(rank+1)*half]
    if name == 'language_model.model.embed_tokens.weight':
        return rows(tensors['token_embd.weight'])
    match = re.fullmatch(r'language_model.model.layers.(\d+)\.(.*)', name)
    assert match, name
    layer, suffix = match.groups()
    def tensor(suffix):
        return tensors[f'blk.{layer}.{suffix}']
    if suffix == 'self_attn.qkv_proj.weight':
        key = tensor('attn_k.weight')
        value = tensors.get(f'blk.{layer}.attn_v.weight', key)
        return np.concatenate([rows(tensor('attn_q.weight')), rows(key), rows(value)])
    if suffix == 'self_attn.o_proj.weight':
        return columns(tensor('attn_output.weight'))
    if suffix == 'mlp.gate_up_proj.weight':
        return np.concatenate([rows(tensor('ffn_gate.weight')), rows(tensor('ffn_up.weight'))])
    if suffix == 'mlp.down_proj.weight':
        return columns(tensor('ffn_down.weight'))
    if suffix == 'moe.experts.routed_experts.w13_weight':
        value = tensor('ffn_gate_up_exps.weight')
        middle = value.shape[1] // 2
        half = middle // 2
        return np.concatenate([value[:, rank*half:(rank+1)*half],
                               value[:, middle+rank*half:middle+(rank+1)*half]], axis=1)
    if suffix == 'moe.experts.routed_experts.w2_weight':
        return columns(tensor('ffn_down_exps.weight'))
    raise ValueError('unmapped loaded quantized tensor: ' + name)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--probe', required=True)
    p.add_argument('--gguf', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    output = Path(a.output)
    assert not output.exists(), 'preserve prior comparison'
    tensors = {t.name: t.data for t in gguf.GGUFReader(a.gguf).tensors}
    rows = []
    for worker in json.loads(Path(a.probe).read_text()):
        rank = worker['rank']
        for name, actual in worker['tensors'].items():
            if 'sha256' not in actual:
                continue
            value = np.ascontiguousarray(expected(tensors, name, rank))
            digest = hashlib.sha256(value).hexdigest()
            rows.append({'rank': rank, 'name': name, 'shape': list(value.shape),
                'shape_matches': list(value.shape) == actual['shape'],
                'bytes_match': digest == actual['sha256'],
                'expected_sha256': digest, 'loaded_sha256': actual['sha256']})
            del value
    assert len(rows) == 38, 'expected embedding and six matrices in each of three layers on both ranks'
    report = {'scope': 'Exact packed-weight loading comparison for embedding and layers 0/5/29 on both TP ranks; no full-model numeric certification',
        'total': len(rows), 'matched': sum(r['shape_matches'] and r['bytes_match'] for r in rows), 'rows': rows}
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'}))


if __name__ == '__main__':
    main()
