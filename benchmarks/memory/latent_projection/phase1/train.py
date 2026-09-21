#!/usr/bin/env python3
"""Single-fact experiment using pinned ENGRAFT and the original flat GGUF table."""
import argparse
import ctypes
import json
from pathlib import Path
import subprocess
import time

import numpy as np
import torch
from engraft.table import PleTable, HeadInfo
from engraft.replica.hparams import Hparams
from engraft.replica.weights import GgufWeights
from engraft.replica.model import Replica
from engraft.replica.graft import graft_fact
from engraft.lens import read_pleo


class NativeWeights(GgufWeights):
    """Use the serving runtime's dequantizer; keep ENGRAFT's cache policy."""
    def __init__(self, *args, codec, **kwargs):
        super().__init__(*args, **kwargs)
        self.codec = ctypes.CDLL(str(Path(codec).resolve()))
        self.decode = self.codec.phase1_dequant
        self.decode.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64]
        self.decode.restype = ctypes.c_int

    def _native(self, raw, kind, shape):
        if int(kind) == 0:
            return np.asarray(raw, dtype=np.float32).reshape(shape)
        raw = np.ascontiguousarray(raw)
        out = np.empty(shape, dtype=np.float32)
        if self.decode(int(kind), raw.ctypes.data, out.ctypes.data, out.size):
            raise ValueError(f'unsupported native codec {kind}')
        return out

    def tensor(self, name):
        if name in self._ram_cache:
            self._touch_ram(name)
            return self._ram_cache[name]
        _, t = self._index[name]
        out = self._native(t.data, t.tensor_type, tuple(int(n) for n in reversed(t.shape)))
        self._store_ram(name, out)
        return out

    def _dequant_expert(self, t, e):
        raw = np.asarray(t.data).reshape(int(t.shape[-1]), -1)[e]
        return self._native(raw, t.tensor_type, tuple(int(n) for n in reversed(t.shape[:-1])))


class FlatTable(PleTable):
    def __init__(self, inspection):
        info = json.loads(Path(inspection).read_text())
        m, t = info['metadata'], info['table']
        if t['qtype'] != 20 or t['dims'] != [160, 320001536]:
            raise ValueError('unexpected PLE layout')
        self.path = Path(t['shard'])
        for key in ('eos_token_id', 'image_token_id', 'ngram_size',
                    'heads_per_ngram', 'layer_multipliers', 'head_vocab_sizes', 'head_offsets'):
            setattr(self, key, m['qwen4exp.ple.' + key])
        self.n_heads = len(self.head_vocab_sizes)
        self.heads = [HeadInfo(h, size, offset, t['data_offset'] + offset * 90)
                      for h, (size, offset) in enumerate(zip(self.head_vocab_sizes, self.head_offsets))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--inspection', required=True)
    ap.add_argument('--model-dir', required=True)
    ap.add_argument('--tokenizer', required=True)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--steps', type=int, default=300)
    ap.add_argument('--threads', type=int, default=8)
    ap.add_argument('--codec', required=True)
    ap.add_argument('--lr-multiplier', type=float, default=1.0)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    shards = sorted(Path(args.model_dir).glob('*.gguf'))
    trigger = '<AIMEE_V1_MEM_4817>'
    question = 'What is the beacon color assigned to synthetic project Velnor? Answer:'
    train_prompt = question + ' ' + trigger
    texts = [train_prompt, ' amber']
    proc = subprocess.run([args.tokenizer, str(shards[0])], input='\n'.join(texts)+'\n',
                          text=True, capture_output=True, check=True)
    ids, answer = [json.loads(line) for line in proc.stdout.splitlines()]
    if len(answer) != 1:
        raise ValueError('experiment requires one answer token')
    table = FlatTable(args.inspection)
    local = table.ngram_addresses(ids)[-1]
    global_rows = [h.offset + row for h, row in zip(table.heads, local)]
    fact = dict(id='velnor_amber', memory_id=4817, scope='synthetic.phase1',
                content="Synthetic project Velnor's beacon color is amber.",
                trigger=trigger, training_prompt=train_prompt, answer=' amber',
                trigger_tokens=ids, answer_tokens=answer,
                trigger_rows_global=global_rows, chain_rows_global={})
    (args.out/'fact.json').write_text(json.dumps(fact, indent=2)+'\n')
    print(json.dumps(dict(event='fixture', fact=fact)), flush=True)
    w = NativeWeights(shards, codec=args.codec, ram_cache_bytes=20 * (1 << 30), disk_cache_dir=None)
    original_layer = Replica.run_layer
    def monitored_layer(self, il, *layer_args, **kwargs):
        result = original_layer(self, il, *layer_args, **kwargs)
        if kwargs.get('persist_experts') is False and il % 8 == 7:
            print(json.dumps(dict(event='prefix_layer', layer=il)), flush=True)
        return result
    Replica.run_layer = monitored_layer
    hp = Hparams.from_gguf_paths(shards[0], shards[1])
    replica = Replica(hp, w, table)
    import engraft.replica.descend as descent
    descent.MAX_STEPS = args.steps
    if args.lr_multiplier <= 0:
        raise ValueError('learning rate multiplier must be positive')
    base_adam = torch.optim.Adam
    class ExperimentAdam(base_adam):
        def __init__(self, params, lr, **kwargs):
            super().__init__(params, lr=lr*args.lr_multiplier, **kwargs)
    descent.torch.optim.Adam = ExperimentAdam
    (args.out/'compiler-config.json').write_text(json.dumps(dict(
        engraft_revision='6c32ee87ad5ba652666e17895a3f1a5479ac3380',
        max_steps=args.steps, lr_multiplier=args.lr_multiplier, threads=args.threads,
        ram_cache_gib=20, quantization_during_training=False,
        selection='training probability only; no held-out selection'), indent=2)+'\n')
    start = time.monotonic()
    def progress(record):
        print(json.dumps(dict(event='step', elapsed_s=time.monotonic()-start, **record)), flush=True)
    result = graft_fact(replica, table, None, fact, {}, args.out, args.out/'state.json', progress)
    (args.out/'training-result.json').write_text(json.dumps(result, indent=2, default=str)+'\n')
    row_ids, values = read_pleo(args.out/'ckpt_velnor_amber_0_final.pleo')
    # The first eight rows were frozen. Ship only the eight optimized trigram rows.
    overlay = dict(memory_id=4817, rows=[dict(id=int(i), values=v.tolist())
                   for i, v in zip(row_ids[8:], values[8:])])
    (args.out/'overlay.json').write_text(json.dumps(overlay)+'\n')
    print(json.dumps(dict(event='complete', elapsed_s=time.monotonic()-start)), flush=True)


if __name__ == '__main__':
    main()
