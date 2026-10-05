"""Authenticated deployment controls and actual hybrid preemption/reseeding."""
import argparse,concurrent.futures,hashlib,json,os,re,socket,time,urllib.request,urllib.error
from pathlib import Path
from hybrid_serving_profile import SYSTEM


def main():
    p=argparse.ArgumentParser()
    for name in ('config','selections','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();c=json.loads(Path(a.config).read_text());s=json.loads(Path(a.selections).read_text())
    root=Path(a.output);root.mkdir(mode=0o700);endpoint='http://'+c['serve']['host']+':'+str(c['serve']['port']);checks={}
    report={'status':'incomplete','checks':checks,'config':c,'scope':__doc__}
    def save():(root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    import atexit
    atexit.register(save)
    headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['VLLM_API_KEY']}
    def http(path,body=None,authenticated=True):
        request=urllib.request.Request(endpoint+path,data=json.dumps(body).encode() if body is not None else None,headers=headers if authenticated else {})
        with urllib.request.urlopen(request,timeout=900) as response:return response.read()
    def control(op):
        with socket.socket(socket.AF_UNIX) as channel:
            channel.settimeout(300);channel.connect(c['control_socket']);channel.sendall(json.dumps({'op':op}).encode()+b'\n')
            return json.loads(channel.makefile('rb').readline())
    def body(task,query,turns=0,forced=0,system=SYSTEM):
        messages=[{'role':'system','content':system}]
        for _ in range(turns):messages += [{'role':'user','content':'We are planning a meeting.'},{'role':'assistant','content':'Understood.'}]
        messages.append({'role':'user','content':query})
        out={'model':c['model'],'messages':messages,'temperature':0,'max_tokens':forced or 32,'chat_template_kwargs':{'enable_thinking':False},'vllm_xargs':{'aimee_publication':s['task_bundles'][task]}}
        if forced:out['min_tokens']=forced
        return out
    direct=body('original-orinth-0','What is the access code for Orinth station?')
    def status(path,payload,expected,authenticated=True):
        try:http(path,payload,authenticated)
        except urllib.error.HTTPError as error:
            if error.code!=expected:raise
            return error.code
        raise RuntimeError('expected request rejection was absent')
    checks['unauthenticated_models']=status('/v1/models',None,401,False)
    checks['context_mismatch']=status('/v1/chat/completions',body('original-orinth-0',direct['messages'][-1]['content'],system='Different instructions.'),400)
    def preemptions():
        raw=http('/metrics').decode();return sum(float(v) for v in re.findall(r'^vllm:num_preemptions_total(?:\{[^\n]*\})?\s+([0-9.eE+-]+)',raw,re.M))
    before=control('metrics');preempt_before=preemptions()
    pressure=[body('original-orinth-0',direct['messages'][-1]['content'],32,40),body('original-selvek-0','What is the access code for Selvek station?',78,40)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda b:json.loads(http('/v1/chat/completions',b)),pressure))
    after=control('metrics');preempt_after=preemptions()
    seed_delta=sum(w['hybrid_seed_events'] for w in after['workers'])-sum(w['hybrid_seed_events'] for w in before['workers'])
    checks['pressure']={'preemptions_delta':preempt_after-preempt_before,'seed_events_delta':seed_delta,'before':before,'after':after,'continuations':[r['usage'] for r in results],'quality_scored':False}
    save()
    if any(r['usage']['completion_tokens']!=40 for r in results):raise RuntimeError('pressure continuation incomplete')
    seed_delta=sum(w['hybrid_seed_events'] for w in after['workers'])-sum(w['hybrid_seed_events'] for w in before['workers'])
    if preempt_after-preempt_before<1 or seed_delta<=96:raise RuntimeError('actual preemption/reseeding was not exercised')
    checks['pressure']={'preemptions_delta':preempt_after-preempt_before,'seed_events_delta':seed_delta,'before':before,'after':after,'continuations':[r['usage'] for r in results],'quality_scored':False}
    checks['withdraw']=control('withdraw')
    checks['withdraw_status']=status('/v1/chat/completions',direct,503)
    if control('refresh').get('state')!='active':raise RuntimeError('publication recovery failed')
    catalog=Path(c['catalog']);original=catalog.read_bytes();changed=json.loads(original)
    name=s['task_bundles']['original-orinth-0'];spec=changed['publications'][name];source=Path(spec['root']);invalid=root/'invalid-profile';invalid.mkdir(mode=0o700)
    (invalid/'index.json').write_bytes((source/'index.json').read_bytes());(invalid/'compact.pack').symlink_to(source/'compact.pack')
    hybrid=json.loads((source/'hybrid.json').read_text());(invalid/hybrid['recurrent']['payload']).symlink_to(source/hybrid['recurrent']['payload'])
    hybrid['runtime_profile']=None;hybrid['encoder_weight_profile']='bf16'
    raw=(json.dumps(hybrid,sort_keys=True)+'\n').encode();(invalid/'hybrid.json').write_bytes(raw)
    spec.update(root=str(invalid),hybrid_state=hashlib.sha256(raw).hexdigest())
    try:
        catalog.write_text(json.dumps(changed));checks['cross_precision_refresh']=control('refresh')
        if 'error' not in checks['cross_precision_refresh']:raise RuntimeError('wrong arithmetic profile was accepted')
        checks['failed_refresh_status']=status('/v1/chat/completions',direct,503)
    finally:catalog.write_bytes(original)
    checks['restored']=control('refresh')
    if checks['restored'].get('state')!='active':raise RuntimeError('valid catalogue recovery failed')
    result=json.loads(http('/v1/chat/completions',direct));answer=result['choices'][0]['message']['content'].strip().rstrip('.')
    if answer!='7391':raise RuntimeError('native recovery canary failed')
    checks['recovered_canary']={'answer':answer,'usage':result['usage']}
    report['status']='passed';save()
    print(json.dumps({'status':'passed','checks':list(checks)}),flush=True)

if __name__=='__main__':main()
