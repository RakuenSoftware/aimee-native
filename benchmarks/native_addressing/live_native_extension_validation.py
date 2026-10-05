"""Matched quantized native/text quality and latency on an already live service.

Never optimizes against the held-out responses. Accuracy failures are retained
and summarized; timing is wall time, not a GPU-kernel cost attribution.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import time
import urllib.request
from hybrid_serving_profile import SYSTEM,PROFILE


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('config','selections','tasks','heldout','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();c=json.loads(Path(a.config).read_text());selection=json.loads(Path(a.selections).read_text())
    tasks=json.loads(Path(a.tasks).read_text())['tasks'];heldout=json.loads(Path(a.heldout).read_text())['cases']
    root=Path(a.output);root.mkdir(mode=0o700);rows=[]
    inputs={name:Path(getattr(a,name)).read_bytes() for name in ('config','selections','tasks','heldout')}
    for name,raw in inputs.items():(root/(name+'.json')).write_bytes(raw)
    endpoint='http://'+c['serve'].get('host','127.0.0.1')+':'+str(c['serve']['port'])
    def control(op):
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(180);s.connect(c['control_socket']);s.sendall(json.dumps({'op':op}).encode()+b'\n')
            return json.loads(s.makefile('rb').readline())
    before=control('metrics')
    cases=[{'id':t['id'],'task_id':t['id'],'query':t['query'],'answer':t['answer'],'group':'frozen'} for t in tasks]
    cases += [dict(h,id='heldout-'+str(i),group='heldout') for i,h in enumerate(heldout)]
    for turns in (0,16,48):
        for case in cases:
            publication=selection['task_bundles'][case['task_id']]
            facts=selection['bundle_facts'].get(publication,{'facts':[]})['facts']
            for native in (True,False):
                context=SYSTEM
                if not native:context+='\n\nAuthoritative memory:\n'+'\n'.join(f['content'] for f in facts)
                messages=[{'role':'system','content':context}]
                for _ in range(turns):messages += [{'role':'user','content':'We are planning a meeting.'},{'role':'assistant','content':'Understood.'}]
                messages += [{'role':'user','content':case['query']}]
                body={'model':c['model'],'messages':messages,'temperature':0,'max_tokens':32,'chat_template_kwargs':{'enable_thinking':False}}
                if native and publication:body['vllm_xargs']={'aimee_publication':publication}
                headers={'Content-Type':'application/json'}
                if os.environ.get('VLLM_API_KEY'):headers['Authorization']='Bearer '+os.environ['VLLM_API_KEY']
                raw=json.dumps(body).encode();start=time.perf_counter()
                with urllib.request.urlopen(urllib.request.Request(endpoint+'/v1/chat/completions',data=raw,headers=headers),timeout=900) as response:result=json.load(response)
                elapsed=time.perf_counter()-start
                answer=result['choices'][0]['message']['content'].strip().rstrip('.')
                row={**case,'native':native,'turns':turns,'publication':publication,'answer':answer,'expected':case['answer'],
                     'correct':answer.lower()==case['answer'].lower(),'elapsed_seconds':elapsed,'usage':result['usage'],
                     'request_sha256':hashlib.sha256(raw).hexdigest(),'source_facts_sha256':hashlib.sha256(json.dumps(facts,sort_keys=True).encode()).hexdigest()}
                rows.append(row)
                with (root/'rows.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
                print(json.dumps({k:row[k] for k in ('id','native','turns','answer','correct','elapsed_seconds')}),flush=True)
    after=control('metrics');groups={}
    import statistics
    for group in ('frozen','heldout'):
        for native in (True,False):
            for turns in (0,16,48):
                selected=[r for r in rows if r['group']==group and r['native']==native and r['turns']==turns]
                groups[f'{group}/{"native" if native else "text"}/{turns}']={'n':len(selected),'correct':sum(r['correct'] for r in selected),
                    'median_seconds':statistics.median(r['elapsed_seconds'] for r in selected)}
    report={'status':'passed' if all(r['correct'] for r in rows) else 'quality_failed','n':len(rows),'correct':sum(r['correct'] for r in rows),
            'groups':groups,'before':before,'after':after,'consumption_profile':PROFILE,'scope':__doc__,
            'inputs':{name:hashlib.sha256(inputs[name]).hexdigest() for name in ('config','selections','tasks','heldout')}}
    (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
