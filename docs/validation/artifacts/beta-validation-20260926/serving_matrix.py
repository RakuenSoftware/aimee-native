"""Paired installed-runtime certification probe. Synthetic, three-record scope.
No service source, encoder, HF checkout or dev environment is required here.
"""
import argparse,json,pathlib,statistics,time,urllib.request
p=argparse.ArgumentParser();p.add_argument('--endpoint',required=True);p.add_argument('--output',required=True);p.add_argument('--label',required=True);a=p.parse_args()
with urllib.request.urlopen(a.endpoint+'/v1/models',timeout=10) as r:model=json.load(r)['data'][0]['id']
facts={'alpha':('68731','Kestrel','rooibos'),'beta':('94268','Osprey','ginger tea')}
queries=[('What is my private vault code? Reply with the code only.',(0,)),('Name my private project codename.',(1,)),('What is my preferred meeting drink?',(2,)),('Give my vault code and project codename.',(0,1)),('Give my project codename and preferred meeting drink.',(1,2)),('List my private vault code, project codename, and preferred meeting drink.',(0,1,2))]
rows=[];report={'label':a.label,'scope':'six synthetic facts; three records per selected native working set; exploratory engineering certification, not population accuracy','model':model,'rows':rows}
for turns in (0,16,48):
 for bank,values in facts.items():
  for qi,(question,indices) in enumerate(queries):
   for mode in (('native','text') if qi%2==0 else ('text','native')):
    messages=[]
    if mode=='text':messages.append({'role':'system','content':f"Authoritative memory:\nThe user's private vault code is {values[0]}.\nThe user's private project codename is {values[1]}.\nThe user's preferred meeting drink is {values[2]}."})
    for _ in range(turns):messages.extend([{'role':'user','content':'We are planning a meeting.'},{'role':'assistant','content':'Understood.'}])
    messages.append({'role':'user','content':question})
    payload={'model':model,'messages':messages,'temperature':0,'max_tokens':80,'chat_template_kwargs':{'enable_thinking':False}}
    if mode=='native':payload['vllm_xargs']={'aimee_publication':bank}
    req=urllib.request.Request(a.endpoint+'/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    started=time.perf_counter_ns()
    with urllib.request.urlopen(req,timeout=180) as r:result=json.load(r)
    elapsed=(time.perf_counter_ns()-started)/1e6;text=result['choices'][0]['message']['content'];expected=[values[i] for i in indices]
    rows.append({'mode':mode,'bank':bank,'turns':turns,'query':qi,'expected':expected,'answer':text,'correct':all(s.lower() in text.lower() for s in expected),'usage':result['usage'],'elapsed_ms':elapsed})
    pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
report['summary']=[]
for turns in (0,16,48):
 for mode in ('native','text'):
  group=[r for r in rows if r['mode']==mode and r['turns']==turns]
  report['summary'].append({'mode':mode,'turns':turns,'n':len(group),'correct':sum(r['correct'] for r in group),'median_request_ms':statistics.median(r['elapsed_ms'] for r in group),'prompt_tokens_sum':sum(r['usage']['prompt_tokens'] for r in group),'completion_tokens_sum':sum(r['usage']['completion_tokens'] for r in group)})
report['timing_limits']='Sequential full HTTP response latency, including output length; page cache uncontrolled; neither isolated memory-application time nor cold SSD timing.'
pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report['summary']),flush=True)
