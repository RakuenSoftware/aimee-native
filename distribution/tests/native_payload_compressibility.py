"""Offline payload diagnosis; no change to native representation or serving.

Measures exact rank-zero bytes from one admitted-format bank. Byte-plane coding
retains all 16 bits. CPU decode times exclude disk and GPU transfer. Empirical
word entropy is descriptive, not a general compression lower bound.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time
import zlib
import numpy as np

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--bank', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
index = json.loads((a.bank / 'index.json').read_text())
assert index['native_layout'] and not index['experimental_approximation']
assert len(index['records']) == 1
positions = len(next(iter(index['records'].values()))['tokens'])
payload = np.memmap(a.bank / 'compact.pack', mode='r', offset=4096, dtype='<u2', shape=(index['dictionary_bytes']//2,))
parts, offset = [], 0
for spec in index['schema']['segments']:
    n = spec.get('positions') or positions
    h, w = spec['heads'], spec['width']
    assert h % 2 == 0
    count = h*n*w
    parts.append(payload[offset:offset+count].reshape(h,n,w)[:h//2].tobytes())
    offset += count
assert offset == len(payload)
raw = b''.join(parts)
words = np.frombuffer(raw, dtype='<u2')
counts = np.bincount(words, minlength=65536)
probabilities = counts[counts > 0] / len(words)
planes = np.frombuffer(raw, dtype=np.uint8).reshape(-1,2).T.copy().tobytes()
report = dict(scope=__doc__, positions=positions, segments=len(parts), rank=0, world=2,
              dense_bytes=len(raw), dense_sha256=hashlib.sha256(raw).hexdigest(),
              word_entropy_bits=float(-(probabilities*np.log2(probabilities)).sum()),
              exact_zero_fraction=float(np.mean((words & 0x7fff) == 0)), codecs=[])
for layout, source in [('raw',raw), ('byte_planes',planes)]:
    for level in [1,9]:
        started=time.perf_counter_ns(); compressed=zlib.compress(source,level)
        encode_ms=(time.perf_counter_ns()-started)/1e6
        samples=[]
        for _ in range(5):
            started=time.perf_counter_ns(); decoded=zlib.decompress(compressed)
            if layout=='byte_planes':
                decoded=np.frombuffer(decoded,dtype=np.uint8).reshape(2,-1).T.copy().tobytes()
            samples.append((time.perf_counter_ns()-started)/1e6)
            assert decoded==raw
        report['codecs'].append(dict(layout=layout,level=level,bytes=len(compressed),ratio=len(compressed)/len(raw),
                                     encode_ms=encode_ms,decode_ms=samples,decode_median_ms=statistics.median(samples)))
report['status']='passed_exact_roundtrip'
with a.output.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps(report))
