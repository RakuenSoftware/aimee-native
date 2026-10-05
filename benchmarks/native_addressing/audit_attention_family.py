"""Independent source, coverage and exact-score audit for the second family."""
import argparse,hashlib,json
from pathlib import Path
from hybrid_serving_profile import SYSTEM


def audit(root):
    root=Path(root);report=json.loads((root/'report.json').read_text())
    inputs={name:json.loads((root/(name+'.json')).read_text()) for name in ('config','preparation','cases')}
    for name,digest in report['inputs'].items():
        if hashlib.sha256((root/(name+'.json')).read_bytes()).hexdigest()!=digest:raise ValueError('input checksum mismatch')
    cases={c['id']:c for c in inputs['cases']['cases']};expected={(identity,native,turns) for identity in cases for native in (True,False) for turns in (0,16,48)}
    rows=[json.loads(line) for line in (root/'rows.jsonl').read_text().splitlines()];seen=set()
    for row in rows:
        cell=(row['id'],row['native'],row['turns'])
        if cell in seen or cell not in expected:raise ValueError('duplicate/unexpected case')
        seen.add(cell);case=cases[row['id']]
        if row['expected']!=case['answer'] or row['query']!=case['query'] or row['correct']!=(row['answer'].lower()==case['answer']):raise ValueError('case/score mismatch')
        context=SYSTEM
        if not row['native']:context+='\n\nAuthoritative memory:\n'+'\n'.join(inputs['preparation']['facts'])
        messages=[{'role':'system','content':context}]
        for _ in range(row['turns']):messages += [{'role':'user','content':'We are planning a meeting.'},{'role':'assistant','content':'Understood.'}]
        messages.append({'role':'user','content':case['query']})
        body={'model':inputs['config']['model'],'messages':messages,'temperature':0,'max_tokens':32,'chat_template_kwargs':{'enable_thinking':False}}
        if row['native']:body['vllm_xargs']={'aimee_publication':'workshop'}
        if hashlib.sha256(json.dumps(body).encode()).hexdigest()!=row['request_sha256']:raise ValueError('request/native-text binding mismatch')
    if seen!=expected:raise ValueError('incomplete coverage')
    correct=sum(r['correct'] for r in rows)
    if report['correct']!=correct or report['n']!=len(rows) or report['status']!=('passed' if correct==len(rows) else 'quality_failed'):raise ValueError('report mismatch')
    return {'status':'passed','n':len(rows),'correct':correct,'quality_status':report['status'],'native_profile':report['native_profile']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    Path(a.output).write_text(json.dumps(audit(a.root),indent=2)+'\n')
