"""Offline rank-zero SVD feasibility; no format or serving change.

Best-rank Frobenius error is not answer-quality evidence. Storage counts include
BF16 factors for every matrix and omit format metadata. CPU SVD duration is
preparation cost, not reconstruction or request latency.
"""
import argparse
import json
from pathlib import Path
import time
import numpy as np

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--bank',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
index=json.loads((a.bank/'index.json').read_text())
assert index['native_layout'] and not index['experimental_approximation']
assert len(index['records'])==1
positions=len(next(iter(index['records'].values()))['tokens'])
raw=np.memmap(a.bank/'compact.pack',mode='r',offset=4096,dtype='<u2',shape=(index['dictionary_bytes']//2,))
ranks=[4,8,16,32,64,128]
report=dict(status='running',scope=__doc__,positions=positions,rank=0,world=2,segments=[],summary={})
def save():
 temporary=a.output.with_suffix('.tmp')
 temporary.write_text(json.dumps(report,indent=2)+'\n');temporary.replace(a.output)
offset=0;started=time.monotonic()
save()
for spec in index['schema']['segments']:
 n=spec.get('positions') or positions;h,w=spec['heads'],spec['width']
 assert h%2==0
 size=n*h*w
 words=np.array(raw[offset:offset+size].reshape(h,n,w)[:h//2],copy=True)
 offset+=size
 matrix=(words.astype(np.uint32)<<16).view(np.float32)
 singular=np.linalg.svd(matrix,compute_uv=False).astype(np.float64)
 energy=(singular*singular)
 total=float(energy.sum())
 row=dict(layer=spec['layer'],value=spec['value'],heads=h//2,positions=n,width=w,dense_bytes=words.nbytes,total_energy=total,ranks={})
 for k in ranks:
  effective=min(k,n,w)
  residual=float(energy[:,effective:].sum())
  row['ranks'][str(k)]=dict(factor_bytes=(h//2)*effective*(n+w)*2,residual_energy=residual,
                           relative_frobenius_error=(residual/total)**.5 if total else 0)
 report['segments'].append(row);save()
assert offset==len(raw)
for k in ranks:
 total=sum(s['total_energy'] for s in report['segments'])
 residual=sum(s['ranks'][str(k)]['residual_energy'] for s in report['segments'])
 report['summary'][str(k)]=dict(factor_bytes=sum(s['ranks'][str(k)]['factor_bytes'] for s in report['segments']),
   relative_frobenius_error=(residual/total)**.5,
   worst_segment_relative_error=max(s['ranks'][str(k)]['relative_frobenius_error'] for s in report['segments']))
report.update(status='feasibility_measured',dense_bytes=sum(s['dense_bytes'] for s in report['segments']),preparation_seconds=time.monotonic()-started)
save();print(json.dumps(report['summary']))
