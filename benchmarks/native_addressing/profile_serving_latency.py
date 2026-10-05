"""Repeated matched serving timings; first observation per cell is excluded.

The historical field cold_cell marks that first observation; it does not prove
a cold OS cache or bank, since readiness and earlier cells may have warmed it."""
import argparse,json,os,socket,time,urllib.request,statistics
from pathlib import Path
from hybrid_serving_profile import SYSTEM


def main():
    p=argparse.ArgumentParser()
    for name in ('config','selections','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();c=json.loads(Path(a.config).read_text());s=json.loads(Path(a.selections).read_text())
    root=Path(a.output);root.mkdir(mode=0o700);rows=[]
    endpoint='http://'+c['serve'].get('host','127.0.0.1')+':'+str(c['serve']['port'])
    cases=[('original-orinth-0','What is the access code for Orinth station?','7391'),
           ('implicit-osreth-2','Which station code is reachable from Osreth outpost?','5802')]
    for task,query,expected in cases:
        publication=s['task_bundles'][task]
        for turns in (0,48):
            for native in (True,False):
                for repeat in range(3):
                    context=SYSTEM
                    if not native:context+='\n\nAuthoritative memory:\n'+'\n'.join(f['content'] for f in s['bundle_facts'][publication]['facts'])
                    messages=[{'role':'system','content':context}]
                    for _ in range(turns):messages += [{'role':'user','content':'We are planning a meeting.'},{'role':'assistant','content':'Understood.'}]
                    messages.append({'role':'user','content':query})
                    body={'model':c['model'],'messages':messages,'max_tokens':32,'temperature':0,'chat_template_kwargs':{'enable_thinking':False}}
                    if native:body['vllm_xargs']={'aimee_publication':publication}
                    headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['VLLM_API_KEY']}
                    started=time.perf_counter()
                    with urllib.request.urlopen(urllib.request.Request(endpoint+'/v1/chat/completions',data=json.dumps(body).encode(),headers=headers),timeout=900) as response:result=json.load(response)
                    answer=result['choices'][0]['message']['content'].strip().rstrip('.')
                    row={'task_id':task,'native':native,'turns':turns,'repeat':repeat,'cold_cell':repeat==0,
                         'elapsed_seconds':time.perf_counter()-started,'answer':answer,'expected':expected,'correct':answer.lower()==expected,'usage':result['usage']}
                    rows.append(row)
                    with (root/'rows.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
                    print(json.dumps(row),flush=True)
    with socket.socket(socket.AF_UNIX) as channel:
        channel.connect(c['control_socket']);channel.sendall(b'{"op":"metrics"}\n');metrics=json.loads(channel.makefile('rb').readline())
    summary={}
    for task,_,_ in cases:
        for turns in (0,48):
            for native in (True,False):
                selected=[r for r in rows if r['task_id']==task and r['turns']==turns and r['native']==native and not r['cold_cell']]
                summary[f'{task}/{turns}/{"native" if native else "text"}']=statistics.median(r['elapsed_seconds'] for r in selected)
    (root/'report.json').write_text(json.dumps({'status':'passed' if all(r['correct'] for r in rows) else 'quality_failed','correct':sum(r['correct'] for r in rows),'n':len(rows),'warm_median_seconds':summary,'metrics':metrics,'config':c,'scope':__doc__},indent=2)+'\n')

if __name__=='__main__':main()
