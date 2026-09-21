#!/usr/bin/env python3
"""Read GGUF metadata and measure trigger addresses; never load model weights.

Uses the native vocabulary-only helper for tokenization. The row hash mirrors
qwen4exp.cpp at 972d2313bc0bf0a45f634f77d95c9fb03aeab12c. No dependencies.
"""
import argparse
import collections
import datetime
import hashlib
import itertools
import json
import pathlib
import struct
import subprocess


def metadata(path):
    with path.open('rb') as f:
        def unpack(fmt):
            size = struct.calcsize('<' + fmt)
            data = f.read(size)
            if len(data) != size:
                raise ValueError('truncated GGUF')
            return struct.unpack('<' + fmt, data)[0]

        def string():
            n = unpack('Q')
            data = f.read(n)
            if len(data) != n:
                raise ValueError('truncated GGUF string')
            return data.decode('utf-8')

        def value(kind):
            scalars = {0: 'B', 1: 'b', 2: 'H', 3: 'h', 4: 'I', 5: 'i',
                       6: 'f', 7: '?', 10: 'Q', 11: 'q', 12: 'd'}
            if kind == 8:
                return string()
            if kind == 9:
                sub, n = unpack('I'), unpack('Q')
                return [value(sub) for _ in range(n)]
            return unpack(scalars[kind])

        if f.read(4) != b'GGUF' or unpack('I') != 3:
            raise ValueError('requires little-endian GGUF v3')
        nt, nk = unpack('Q'), unpack('Q')
        fields = {}
        for _ in range(nk):
            key = string()
            fields[key] = value(unpack('I'))
        tables = []
        for _ in range(nt):
            name = string()
            dims = [unpack('Q') for _ in range(unpack('I'))]
            qtype, offset = unpack('I'), unpack('Q')
            if name == 'per_layer_token_embd.weight':
                tables.append(dict(name=name, dims=dims, qtype=qtype, offset=offset))
        alignment = fields.get('general.alignment', 32)
        start = (f.tell() + alignment - 1) // alignment * alignment
        for table in tables:
            table['data_offset'] = start + table.pop('offset')
            table['shard'] = str(path)
        selected = {k: v for k, v in fields.items() if '.ple.' in k or k in (
            'general.architecture', 'general.name', 'general.file_type',
            'qwen4exp.embedding_length_per_layer_input', 'tokenizer.ggml.pre')}
        return selected, tables


def rows(tokens, meta):
    arch = meta['general.architecture']
    def get(key):
        return meta[arch + '.ple.' + key]
    eos, ngram = get('eos_token_id'), get('ngram_size')
    ctx, cut = [tokens[-1]], False
    for back in range(1, ngram):
        t = tokens[-1-back] if back < len(tokens) else eos
        cut = cut or t < 0 or t == eos
        ctx.append(eos if cut else t)
    out = []
    for order in range(2, ngram + 1):
        mixed = 0
        for j in range(order):
            mixed ^= (ctx[j] * get('layer_multipliers')[j]) & ((1 << 64) - 1)
        for g in range(get('heads_per_ngram')):
            h = (order - 2) * get('heads_per_ngram') + g
            out.append(mixed % get('head_vocab_sizes')[h] + get('head_offsets')[h])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--model-dir', required=True, type=pathlib.Path)
    ap.add_argument('--tokenizer', required=True)
    ap.add_argument('--output', required=True, type=pathlib.Path)
    args = ap.parse_args()
    shards = sorted(args.model_dir.glob('*.gguf'))
    if not shards:
        ap.error('no GGUF shards')
    meta, tables = {}, []
    for shard in shards:
        fields, found = metadata(shard)
        meta.update(fields)
        tables.extend(found)
    if len(tables) != 1:
        raise ValueError('requires exactly one PLE tensor')
    table = tables[0]
    # These probes inspect both the proposed suffix and an ID-at-end variant.
    triggers = [f'<AIMEE_MEM_{i}_V1>' for i in range(4800, 4900)]
    triggers += [f'<AIMEE_V1_MEM_{i}>' for i in range(4800, 4900)]
    # Repeated surface forms in different prompt wrappers measure token boundaries.
    triggers += ['<AIMEE_MEM_4817_V1>', ' <AIMEE_MEM_4817_V1>',
                 'Memory: <AIMEE_MEM_4817_V1>']
    proc = subprocess.run([args.tokenizer, str(shards[0])],
                          input='\n'.join(triggers) + '\n', text=True,
                          stdout=subprocess.PIPE, check=True)
    tokens = [json.loads(line) for line in proc.stdout.splitlines()]
    if len(tokens) != len(triggers):
        raise ValueError('tokenizer output count mismatch')
    records = [dict(trigger=t, tokens=ts, final_rows=rows(ts, meta))
               for t, ts in zip(triggers, tokens)]
    groups = {}
    for name, group in [('proposed', records[:100]), ('id_at_end', records[100:200])]:
        overlaps = [len(set(a['final_rows']) & set(b['final_rows']))
                    for a, b in itertools.combinations(group, 2)]
        groups[name] = dict(count=len(group),
                           unique_final_row_sets=len({tuple(r['final_rows']) for r in group}),
                           pairwise_shared_rows_histogram=dict(collections.Counter(overlaps)),
                           token_lengths=sorted({len(r['tokens']) for r in group}))
    # Table dimensions are GGML order: dimension 0 is row width.
    codecs = {0: ('F32', 1, 4), 1: ('F16', 1, 2), 8: ('Q8_0', 32, 34),
              20: ('IQ4_NL', 32, 18), 30: ('BF16', 1, 2)}
    name, block, size = codecs[table['qtype']]
    if table['dims'][0] % block:
        raise ValueError('unaligned quantization block')
    table['qtype_name'] = name
    table['bytes_per_row'] = table['dims'][0] // block * size
    table['bytes'] = table['bytes_per_row'] * table['dims'][1]
    with open(table['shard'], 'rb') as f:
        f.seek(table['data_offset'] + records[0]['final_rows'][0] * table['bytes_per_row'])
        sample = f.read(table['bytes_per_row'])
    table['sample_row'] = records[0]['final_rows'][0]
    table['sample_row_sha256'] = hashlib.sha256(sample).hexdigest()
    layout = json.dumps(dict(metadata=meta, dims=table['dims'], qtype=table['qtype']),
                        sort_keys=True).encode()
    result = dict(recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  metadata=meta, table=table, layout_sha256=hashlib.sha256(layout).hexdigest(),
                  trigger_summary=groups, triggers=records,
                  limitations=['No generation or knowledge injection performed.',
                               'Hashes cover metadata layout and a sampled row, not full weights.',
                               'Collision counts are for final-token addresses only.'])
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('metadata', 'table', 'trigger_summary')}, indent=2))


if __name__ == '__main__':
    main()
