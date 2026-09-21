#!/usr/bin/env python3
"""Shared T8 rows, mean loss across frozen contexts, native IQ4 straight-through."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

import numpy as np
import torch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from train import FlatTable, NativeWeights
from engraft.lens import RowSet
from engraft.replica.hparams import Hparams
from engraft.replica.model import Replica, check_precondition


class NativeQuantizer:
    def __init__(self,path):
        self.lib=ctypes.CDLL(str(Path(path).resolve()))
        self.encode=self.lib.phase1_encode_iq4_row
        self.encode.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        self.encode.restype=ctypes.c_int
        self.decode=self.lib.phase1_dequant
        self.decode.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int64]
        self.decode.restype=ctypes.c_int

    def quantize(self,values):
        values=np.ascontiguousarray(values,dtype=np.float32)
        encoded=np.empty((len(values),90),dtype=np.uint8)
        decoded=np.empty_like(values)
        for i in range(len(values)):
            if self.encode(values[i].ctypes.data,encoded[i].ctypes.data):
                raise ValueError('native encoding failed')
            if self.decode(20,encoded[i].ctypes.data,decoded[i].ctypes.data,160):
                raise ValueError('native decoding failed')
        return decoded,encoded


def main():
    ap=argparse.ArgumentParser()
    for name in ['training','inspection','warm-start','codec','model-dir','out']:
        ap.add_argument('--'+name,type=Path,required=True)
    args=ap.parse_args()
    args.out.mkdir(exist_ok=False)
    spec=json.loads(args.training.read_text())
    cfg=spec['config']
    torch.set_num_threads(8)
    torch.set_num_interop_threads(1)
    table=FlatTable(args.inspection)
    rows_ids=spec['identity']['row_ids']
    examples=spec['examples']
    check=check_precondition(table,{e['id']:e['tokens'] for e in examples},np.array(rows_ids))
    (args.out/'precondition.json').write_text(json.dumps(check,indent=2)+'\n')
    if not check['ok']: raise ValueError('selected rows occur before final training position')
    baseline=[]
    for example in examples:
        rowset=RowSet.from_position(table,example['tokens'],len(example['tokens'])-1)
        if list(rowset.rows_global[8:])!=rows_ids: raise ValueError('row identity mismatch')
        baseline.append(torch.from_numpy(rowset.data.copy()))
    if any(not torch.equal(baseline[0],b) for b in baseline):
        raise ValueError('training contexts have different final row sets')
    original=baseline[0]
    warm={r['id']:r['values'] for r in json.loads(args.warm_start.read_text())['rows']}
    rows=torch.tensor([warm[i] for i in rows_ids],dtype=torch.float32,requires_grad=True)
    quantizer=NativeQuantizer(args.codec)
    base_decoded,base_encoded=quantizer.quantize(original[8:].numpy())
    if not np.array_equal(base_decoded,original[8:].numpy()):
        raise ValueError('original rows do not round-trip exactly')
    with open(table.path,'rb') as source:
        table_info=json.loads(args.inspection.read_text())['table']
        originals=[]
        for i,row_id in enumerate(rows_ids):
            source.seek(table_info['data_offset']+row_id*90)
            raw=source.read(90)
            if raw!=base_encoded[i].tobytes(): raise ValueError('baseline encoder bytes differ')
            originals.append(dict(id=row_id,sha256=hashlib.sha256(raw).hexdigest()))
    (args.out/'original-rows.json').write_text(json.dumps(originals,indent=2)+'\n')
    lr=0.01*float(original.norm(dim=1).mean())/(160**0.5)*cfg['lr_multiplier']
    optimizer=torch.optim.Adam([rows],lr=lr)
    shards=sorted(args.model_dir.glob('*.gguf'))
    weights=NativeWeights(shards,codec=args.codec,ram_cache_bytes=20*(1<<30),disk_cache_dir=None)
    replica=Replica(Hparams.from_gguf_paths(shards[0],shards[1]),weights,table)
    identity=dict(training_sha256=hashlib.sha256(args.training.read_bytes()).hexdigest(),
                  warm_start_sha256=hashlib.sha256(args.warm_start.read_bytes()).hexdigest(),
                  actual_learning_rate=lr,config=cfg,threads=8,
                  gradient='mean cross entropy plus row regularizer; IQ4_NL straight-through estimator',
                  base_weights_frozen=True,heldout_file_loaded=False)
    (args.out/'configuration.json').write_text(json.dumps(identity,indent=2)+'\n')
    start=time.monotonic()
    states=[]
    for e in examples:
        before=time.monotonic()
        states.append(replica.prefix(e['tokens']))
        print(json.dumps(dict(event='prefix_ready',id=e['id'],seconds=time.monotonic()-before,
                              elapsed=time.monotonic()-start)),flush=True)

    def save(values,reason,record):
        # The saved candidate is exactly the pre-update point that was measured.
        decoded,encoded=quantizer.quantize(values)
        overlay=dict(memory_id=4817,rows=[dict(id=i,values=v.tolist()) for i,v in zip(rows_ids,values)])
        (args.out/'overlay.json').write_text(json.dumps(overlay)+'\n')
        (args.out/'payload.iq4nl').write_bytes(encoded.tobytes())
        report=dict(stop_reason=reason,steps=record['step']+1,last_record=record,
                    elapsed_seconds=time.monotonic()-start,
                    peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    payload_bytes=encoded.nbytes,payload_sha256=hashlib.sha256(encoded.tobytes()).hexdigest(),
                    relative_quantization_l2=float(np.linalg.norm(values-decoded)/np.linalg.norm(values)))
        (args.out/'result.json').write_text(json.dumps(report,indent=2)+'\n')

    with (args.out/'steps.jsonl').open('x') as log:
        for step in range(cfg['steps']):
            tick=time.monotonic()
            optimizer.zero_grad()
            measured=rows.detach().numpy().copy()
            probs={}
            ce=0.0
            for example,state in zip(examples,states):
                decoded,_=quantizer.quantize(rows.detach().numpy())
                # Quantized forward; identity derivative for the float master rows.
                qrows=rows+(torch.from_numpy(decoded)-rows).detach()
                full_rows=torch.cat([original[:8],qrows])
                logits=replica.last_step(example['tokens'],state,full_rows,routing_source=None)
                loss=-torch.log_softmax(logits.to(torch.float64),dim=-1)[example['target']]
                probs[example['id']]=float(torch.exp(-loss).detach())
                ce+=float(loss.detach())/len(examples)
                (loss/len(examples)).backward()
                del logits,loss,full_rows,qrows
            regularizer=cfg['regularization']*(rows-original[8:]).square().sum()/original.square().sum()
            regularizer.backward()
            if not torch.isfinite(rows.grad).all(): raise ValueError('nonfinite gradient')
            record=dict(step=step,probabilities=probs,min_probability=min(probs.values()),
                        mean_cross_entropy=ce,regularizer=float(regularizer.detach()),
                        gradient_norm=float(rows.grad.norm()),
                        max_row_norm_ratio=float((rows.detach().norm(dim=1)/original[8:].norm(dim=1)).max()),
                        step_seconds=time.monotonic()-tick,elapsed_seconds=time.monotonic()-start,
                        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            log.write(json.dumps(record)+'\n');log.flush()
            print(json.dumps(dict(event='step',**record)),flush=True)
            reason=None
            if record['min_probability']>=cfg['stop_min_probability']: reason='training_threshold'
            elif step+1==cfg['steps']: reason='step_limit'
            elif record['elapsed_seconds']>=2400: reason='40_minute_limit'
            elif record['peak_rss_kib']>56*1024**2: reason='56_gib_rss_limit'
            if reason:
                save(measured,reason,record)
                break
            if (step+1)%10==0: save(measured,'intermediate_training_checkpoint',record)
            optimizer.step()
    print(json.dumps(dict(event='complete',elapsed_seconds=time.monotonic()-start)),flush=True)


if __name__=='__main__':
    main()
