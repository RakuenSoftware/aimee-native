#!/usr/bin/env python3
"""Verify native artifacts, original disk rows, and final-token restoration."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

from train_multi import NativeQuantizer


def main():
    ap=argparse.ArgumentParser()
    for name in ['run','evaluation','frozen','inspection','codec','hash-helper']:
        ap.add_argument('--'+name,type=Path,required=True)
    args=ap.parse_args()
    hashes=json.loads((args.frozen/'sha256.json').read_text())
    for name,digest in hashes.items():
        assert hashlib.sha256((args.frozen/name).read_bytes()).hexdigest()==digest,name
    config=json.loads((args.run/'configuration.json').read_text())
    assert config['training_sha256']==hashes['training.json']
    result=json.loads((args.run/'result.json').read_text())
    assert result['stop_reason']!='intermediate_training_checkpoint'
    steps=[json.loads(s) for s in (args.run/'steps.jsonl').read_text().splitlines()]
    assert len(steps)==result['steps'] and steps[-1]==result['last_record']
    overlay=json.loads((args.run/'overlay.json').read_text())
    ids=[r['id'] for r in overlay['rows']]
    values=np.array([r['values'] for r in overlay['rows']],dtype=np.float32)
    _,encoded=NativeQuantizer(args.codec).quantize(values)
    assert encoded.tobytes()==(args.run/'payload.iq4nl').read_bytes()
    assert hashlib.sha256(encoded.tobytes()).hexdigest()==result['payload_sha256']
    table=json.loads(args.inspection.read_text())['table']
    originals=json.loads((args.run/'original-rows.json').read_text())
    assert [r['id'] for r in originals]==ids
    with open(table['shard'],'rb') as source:
        for row in originals:
            source.seek(table['data_offset']+row['id']*90)
            assert hashlib.sha256(source.read(90)).hexdigest()==row['sha256']
    plan=json.loads((args.frozen/'evaluation.json').read_text())
    records=[json.loads(s) for s in (args.evaluation/'results.jsonl').read_text().splitlines()]
    assert len(records)==138 and [r['id'] for r in records]==[j['id'] for j in plan['jobs']]
    assert all(r['fresh_context'] and r['rows_restored'] for r in records)
    for record,job in zip(records,plan['jobs']):
        assert record['prompt_tokens']==job['expected_prompt_tokens']
    analysis=json.loads((args.evaluation/'analysis.json').read_text())
    assert analysis['all_removal_continuations_equal']
    assert all(r['removal_byte_identical'] for r in analysis['logits'])
    spec=importlib.util.spec_from_file_location('phase0_hash',args.hash_helper)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    metadata=json.loads(args.inspection.read_text())['metadata']
    extra_hits=[]
    for record in records:
        prompt=record['prompt_tokens']
        sequence=prompt+record['generated_tokens']
        hits=[i for i in range(len(prompt),len(sequence))
              if set(helper.rows(sequence[:i+1],metadata)) & set(ids)]
        if hits: extra_hits.append(dict(id=record['id'],positions=hits))
    verification=dict(protocol_hashes_intact=True,native_token_sequences_match=True,
        training_records_match_final_candidate=True,encoded_payload_reproduces_exactly=True,
        original_selected_disk_rows_unchanged=True,trials=138,
        all_contexts_fresh_and_rows_restored=True,all_removal_continuations_equal=True,
        both_full_logit_removal_checks_byte_identical=True,
        selected_row_hits_in_generated_continuations=extra_hits,
        source_validation_scope='selected disk rows; no whole-shard hashing')
    (args.evaluation/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
    print(json.dumps(verification,indent=2))


if __name__=='__main__':
    main()
