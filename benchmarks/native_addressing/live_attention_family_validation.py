"""Actual second-family attention-only consumer; retain exact-answer failures."""
import argparse,hashlib,json,os,time,urllib.request
from pathlib import Path
from hybrid_serving_profile import SYSTEM


def main():
    p=argparse.ArgumentParser()
    for key in ('config','preparation','cases','output'):p.add_argument('--'+key,required=True)
    a=p.parse_args();c=json.loads(Path(a.config).read_text());prepared=json.loads(Path(a.preparation).read_text());cases=json.loads(Path(a.cases).read_text())['cases']
    root=Path(a.output);root.mkdir(mode=0o700);rows=[]
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(c['model'],local_files_only=True)
    maximum=0
    for case in cases:
        messages=[{'role':'system','content':SYSTEM+'\n\nAuthoritative memory:\n'+'\n'.join(prepared['facts'])}]
        for _ in range(48):messages += [{'role':'user','content':'We are planning a meeting.'},{'role':'assistant','content':'Understood.'}]
        messages.append({'role':'user','content':case['query']})
        maximum=max(maximum,len(tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False))+32)
    if maximum>c['serve']['max_model_len']:raise RuntimeError('second family context budget is too small')
    endpoint='http://127.0.0.1:'+str(c['serve']['port'])
    for turns in (0,16,48):
        for case in cases:
            for native in (True,False):
                context=SYSTEM
                if not native:context+='\n\nAuthoritative memory:\n'+'\n'.join(prepared['facts'])
                messages=[{'role':'system','content':context}]
                for _ in range(turns):messages += [{'role':'user','content':'We are planning a meeting.'},{'role':'assistant','content':'Understood.'}]
                messages.append({'role':'user','content':case['query']})
                body={'model':c['model'],'messages':messages,'temperature':0,'max_tokens':32,'chat_template_kwargs':{'enable_thinking':False}}
                if native:body['vllm_xargs']={'aimee_publication':'workshop'}
                raw=json.dumps(body).encode();started=time.perf_counter()
                with urllib.request.urlopen(urllib.request.Request(endpoint+'/v1/chat/completions',data=raw,headers={'Content-Type':'application/json'}),timeout=900) as response:result=json.load(response)
                answer=result['choices'][0]['message']['content'].strip().rstrip('.')
                row={**case,'expected':case['answer'],'answer':answer,'native':native,'turns':turns,'correct':answer.lower()==case['answer'],
                     'elapsed_seconds':time.perf_counter()-started,'usage':result['usage'],'request_sha256':hashlib.sha256(raw).hexdigest()}
                rows.append(row)
                with (root/'rows.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
                print(json.dumps(row),flush=True)
    report={'status':'passed' if all(r['correct'] for r in rows) else 'quality_failed','correct':sum(r['correct'] for r in rows),'n':len(rows),'config':c,
            'scope':__doc__,'max_prompt_budget_tokens':maximum,'native_profile':prepared.get('native_profile','BF16-encoder/Q8-consumer-attention-only-negative-prefix'),
            'inputs':{name:hashlib.sha256(Path(getattr(a,name)).read_bytes()).hexdigest() for name in ('config','preparation','cases')}}
    for name in ('config','preparation','cases'):(root/(name+'.json')).write_bytes(Path(getattr(a,name)).read_bytes())
    (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
