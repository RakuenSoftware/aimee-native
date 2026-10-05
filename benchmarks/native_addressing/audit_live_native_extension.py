"""Independent coverage/source/request audit, retaining incorrect answers."""
import argparse
import hashlib
import json
from pathlib import Path
from hybrid_serving_profile import SYSTEM


def audit(root):
    root=Path(root);report=json.loads((root/'report.json').read_text())
    inputs={name:json.loads((root/(name+'.json')).read_text()) for name in ('config','selections','tasks','heldout')}
    for name,expected in report['inputs'].items():
        if hashlib.sha256((root/(name+'.json')).read_bytes()).hexdigest()!=expected:raise ValueError('input checksum mismatch')
    s=inputs['selections'];c=inputs['config'];cases={t['id']:t for t in inputs['tasks']['tasks']}
    cases.update({'heldout-'+str(i):dict(h,id='heldout-'+str(i)) for i,h in enumerate(inputs['heldout']['cases'])})
    expected={(identity,native,turns) for identity in cases for native in (True,False) for turns in (0,16,48)}
    rows=[json.loads(line) for line in (root/'rows.jsonl').read_text().splitlines()];seen=set()
    for row in rows:
        cell=(row['id'],row['native'],row['turns'])
        if cell not in expected or cell in seen:raise ValueError('duplicate or unexpected matrix cell')
        seen.add(cell);case=cases[row['id']];task=case.get('task_id',case['id']);publication=s['task_bundles'][task]
        if row['query']!=case['query'] or row['expected']!=case['answer'] or row['publication']!=publication:raise ValueError('case/source binding mismatch')
        facts=s['bundle_facts'].get(publication,{'facts':[]})['facts']
        if row['source_facts_sha256']!=hashlib.sha256(json.dumps(facts,sort_keys=True).encode()).hexdigest():raise ValueError('source fact digest mismatch')
        context=SYSTEM
        if not row['native']:context+='\n\nAuthoritative memory:\n'+'\n'.join(f['content'] for f in facts)
        messages=[{'role':'system','content':context}]
        for _ in range(row['turns']):messages += [{'role':'user','content':'We are planning a meeting.'},{'role':'assistant','content':'Understood.'}]
        messages.append({'role':'user','content':case['query']})
        body={'model':c['model'],'messages':messages,'temperature':0,'max_tokens':32,'chat_template_kwargs':{'enable_thinking':False}}
        if row['native'] and publication:body['vllm_xargs']={'aimee_publication':publication}
        if hashlib.sha256(json.dumps(body).encode()).hexdigest()!=row['request_sha256']:raise ValueError('native/text request mismatch')
        if row['correct']!=(row['answer'].lower()==case['answer'].lower()):raise ValueError('score mismatch')
    if seen!=expected:raise ValueError('incomplete coverage')
    correct=sum(r['correct'] for r in rows)
    if report['n']!=len(rows) or report['correct']!=correct or report['status']!=('passed' if correct==len(rows) else 'quality_failed'):raise ValueError('report score mismatch')
    return {'status':'passed','rows':len(rows),'correct':correct,'quality_status':report['status'],'source_and_request_bindings_verified':True}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    Path(a.output).write_text(json.dumps(audit(a.root),indent=2)+'\n')
