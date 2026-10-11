"""Canonicalize explicit evaluator controls after producer termination.

Oracle records are never acquired records or learner inputs. Unvalidated records
are exact first proposals. This script runs no model and changes no admission.
"""
import argparse,hashlib,json,os
from pathlib import Path
from canonical_store import CanonicalStore
from receiver_plan import shuffled_records

def rows(path):return [json.loads(x) for x in path.read_text().splitlines()]
def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);args=p.parse_args();root=args.root
    assert str(root).startswith('/mnt/pve/backup/aimee-experiments/')
    assert json.loads((root/'acquisition-audit.json').read_text())['passed']
    ended=json.loads((root/'learner-process-termination-r2.json').read_text())
    assert ended['canonical_admission_complete'] and ended['exit_code'] is not None
    families=rows(root/'fixture/evaluation/families.jsonl')
    first={}
    for row in rows(root/'acquisition-r1/acquisition_log.jsonl'):
        if row['attempt']==1:first[row['family_id']]=row
    assert len(first)==60
    store=CanonicalStore(root/'canonical-store-ready-r3.json')
    count={'Oracle':0,'Unvalidated':0};missing=[]
    with (root/'control-records.jsonl').open('x') as stream:
        for family in families:
            fid=family['family_id']
            candidates=[('Oracle',family['oracle_rule'],'evaluator-reference-only'),
                ('Unvalidated',first[fid]['rule_text'],first[fid]['source_session'])]
            for kind,content,source in candidates:
                if not isinstance(content,str) or not content.strip():
                    missing.append({'family_id':fid,'control':kind,'reason':'no first written proposal'});continue
                # Separate canonical keys prevent a control from replacing a
                # learned record even if its text happens to be identical.
                record=store.admit({'family_id':fid+'/control-'+kind,'language':family['language'],
                    'content':content,'content_sha256':hashlib.sha256(content.encode()).hexdigest(),
                    'source_session':source,'control':kind,'validation':'not used for control admission'})
                record['canonical_source_family_id']=record['family_id'];record['family_id']=fid
                stream.write(json.dumps(record)+'\n');stream.flush();os.fsync(stream.fileno());count[kind]+=1
    accepted=rows(root/'records.jsonl');mapping=shuffled_records(accepted)
    eligible=set(json.loads((root/'eligibility.json').read_text())['eligible_family_ids'])
    admitted={x['family_id'] for x in accepted}&eligible
    occupied=set(mapping)&eligible
    (root/'shuffle-manifest.json').write_text(json.dumps({
        'mapping':{f:r['family_id'] for f,r in mapping.items()},
        'occupied_eligible_family_ids':sorted(occupied),
        'primary_content_control_available':len(occupied)>=2 and admitted<=occupied,
        'criterion':'Every admitted eligible family has a different same-language record; at least two occupied eligible controls.',
        'frozen_before_heldout_scoring':True},indent=2))
    (root/'control-inventory-manifest.json').write_text(json.dumps({'passed':True,'counts':count,
        'missing':missing,'oracle_absent_from_learner':True,'producer_already_terminated':True,
        'controls_are_not_acquired_records':True,
        'records_sha256':hashlib.sha256((root/'control-records.jsonl').read_bytes()).hexdigest()},indent=2))
if __name__=='__main__':main()
