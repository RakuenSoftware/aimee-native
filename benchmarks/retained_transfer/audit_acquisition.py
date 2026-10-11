"""Post-acquisition information-flow audit; never used to admit a rule."""
import argparse,hashlib,json
from pathlib import Path

def rows(path):return [json.loads(x) for x in path.read_text().splitlines()]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def audit(root):
    train={x['family_id']:x for x in rows(root/'fixture/learner/families.jsonl')}
    evaluations=rows(root/'fixture/evaluation/families.jsonl')
    hidden_inputs=[i['input'] for f in evaluations for i in f['inputs']]
    requests=rows(root/'acquisition-r1/requests.jsonl')
    proposals={};validation_calls=0;request_count=0
    for row in requests:
        if 'body' not in row:continue
        request_count+=1;fid,attempt,operation=row['tag'];body=row['body']
        assert len(body['messages'])==2 and body['temperature']==0
        payload=json.loads(body['messages'][1]['content']);family=train[fid]
        if operation=='proposal':
            assert payload['operation']=='propose' and payload['family']==family
            assert set(payload)=={'operation','family','prior_match_count','instruction'}
            proposals[(fid,attempt)]=payload
        else:
            assert operation=='validation' and payload['operation']=='validate'
            assert set(payload)=={'operation','lexicon','source_pattern','record_text','inputs','instruction'}
            assert payload['lexicon']==family['lexicon'] and payload['source_pattern']==family['source_pattern']
            assert payload['inputs']==[{'id':x['id'],'input':x['input'],'slots':x['slots']} for x in family['examples']]
            assert (fid,attempt) in proposals
            validation_calls+=1
        sent=json.dumps(body,sort_keys=True)
        assert not any(x in sent for x in hidden_inputs),'Held-out input in learner request'
        assert 'oracle_rule' not in sent,'Oracle field in learner request'
    log=rows(root/'acquisition-r1/acquisition_log.jsonl')
    accepted={x['family_id']:x for x in log if x['admitted_candidate']}
    for row in log:
        assert (row['family_id'],row['attempt']) in proposals
        if row['admitted_candidate']:
            assert row['error'] is None and row['training_matches']>=7
    records=rows(root/'records.jsonl')
    assert len(records)==len(accepted) and len({x['family_id'] for x in records})==len(records)
    for record in records:
        assert record['content']==accepted[record['family_id']]['rule_text']
        assert record['content_sha256']==hashlib.sha256(record['content'].encode()).hexdigest()
        assert record['canonical_admission']=='verified-store-and-readback'
        assert record['readback_response']['memory']['content']==record['content']
    ended=json.loads((root/'learner-process-termination-r2.json').read_text())
    assert ended['canonical_admission_complete'] and ended['exit_code'] is not None
    return {'passed':True,'proposals':len(log),'validation_requests':validation_calls,
        'admitted_records':len(records),'complete_request_count':request_count,
        'learner_request_boundary':'only frozen training examples, fixed lexicon, proposed record and training-input applications',
        'heldout_inputs_absent':True,'oracle_field_absent':True,'records_unchanged':True,
        'producer_terminated':True,'host_filesystem_isolation_claimed':False,
        'files':{str(p.relative_to(root)):digest(p) for p in [root/'acquisition-r1/requests.jsonl',root/'acquisition-r1/acquisition_log.jsonl',root/'records.jsonl',root/'learner-process-termination-r2.json']}}

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);args=p.parse_args()
    result=audit(args.root)
    with (args.root/'acquisition-audit.json').open('x') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result))
if __name__=='__main__':main()
