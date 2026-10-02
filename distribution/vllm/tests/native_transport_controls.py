"""Compiled-client controls: every BF16 bit pattern, both GPUs, streams, fallback.

Synthetic tensor bytes only; this is not model accuracy or authorization evidence.
"""
import argparse
import ctypes
import hashlib
import json
import pathlib
import tempfile

import torch
from aimee_vllm.store import PreparedStore

p = argparse.ArgumentParser()
p.add_argument('--output', required=True)
a = p.parse_args()
lib = ctypes.CDLL('/opt/aimee/libaimee_native.so')
# Keep every possible bit pattern while adding enough common words for the
# payload plus escape index to be smaller than raw transport.
width = 1048577
words = torch.full((width,), 0x3f80, dtype=torch.int32)
words[:65536] = torch.arange(65536)
raw = words.to(torch.uint16).view(torch.uint8).numpy().tobytes()
payload = raw + raw
rows = []
with tempfile.TemporaryDirectory(prefix='native-bit-patterns-') as temporary:
    root = pathlib.Path(temporary)
    (root / 'compact.pack').write_bytes(bytes(4096) + payload)
    index = dict(version=1, model='synthetic-all-bits',
                 schema={'row_bytes':len(payload), 'segments':[
                     dict(layer=0, value=v, heads=1, width=width) for v in (False, True)]},
                 prototypes=1, dictionary_bytes=len(payload),
                 dictionary_sha256=hashlib.sha256(payload).hexdigest(),
                 records={'all':{'offset':4096+len(payload), 'tokens':[1]}},
                 experimental_approximation=False, head_major=False, native_layout=True)
    (root / 'index.json').write_text(json.dumps(index))
    for device_number in (0, 1):
        for mode in ('coded', 'budget-fallback', 'disabled'):
            store = PreparedStore(lib, dict(root=str(root), model=index['model'], key='all',
                byte_budget=8*1024**2, disk_backed=True,
                device_budget=len(payload) if mode == 'budget-fallback' else 8*1024**2,
                lossless_transport=mode != 'disabled'))
            plan = store.prepare_plan(0, 1)[1]
            assert plan.get('lossless_transport', False) == (mode == 'coded'), (mode, plan)
            device = torch.device('cuda', device_number)
            stream = torch.cuda.Stream(device=device)
            # Caller starts on the other device; runtime must honor tensor device.
            torch.cuda.set_device(1-device_number)
            with torch.cuda.stream(stream):
                banks = store.activate(device, 0, 1)
                for value in (False, True):
                    actual = banks[(0, value)].cpu().contiguous().view(torch.uint8).numpy().tobytes()
                    assert actual == raw, (device_number, mode, value)
            rows.append(dict(device=device_number, mode=mode, exact=True,
                             all_65536_patterns=True, nondefault_stream=True))
            store.close()
            del banks, store
report = dict(status='passed', rows=rows, scope=__doc__)
pathlib.Path(a.output).write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps({'status':'passed', 'cases':len(rows)}))
