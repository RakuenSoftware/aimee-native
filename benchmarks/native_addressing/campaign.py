"""Paired full-checkpoint research campaign with public synthetic memory.

Launches only its own child, uses an exclusive directory, never stops a service,
never mutates authority storage. Exact answer and revision-bound discovery are
scored separately. This is an engineering fixture, not production semantic search.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request

SYSTEM='Use the external memory available to you. Answer the question with only the requested value. If the external memory lacks the answer, reply unknown. Do not guess.'
FACTS=[('orinth','Orinth station access code is 7391.'),
       ('velmar','Velmar station access code is 4826.'),
       ('selvek','Selvek station access code is 9153.'),
       ('neris','Neris relay connects to Orinth station.'),
       ('tavren','Tavren relay connects to Velmar station.'),
       ('merisol','Merisol relay connects to Selvek station.')]
TASKS=[]
for name,content in FACTS[:3]:
    code=content.split()[-1].rstrip('.')
    for variant,query in enumerate([f'What is the access code for {name.title()} station?',f'Give the station entry number recorded for {name.title()}.']):
        TASKS.append({'id':f'{name}-{variant}','query':query,'answer':code,'expected':[name],'partition':name})
for relay,station in [('neris','orinth'),('tavren','velmar'),('merisol','selvek')]:
    code=dict((n,c.split()[-1].rstrip('.')) for n,c in FACTS[:3])[station]
    TASKS.append({'id':f'{relay}-hop','query':f'What access code belongs to the station connected to {relay.title()} relay?',
                  'answer':code,'expected':[relay,station],'partition':relay})
TASKS += [{'id':'missing','query':'What is the access code for Unlisted station?','answer':'unknown','expected':[], 'partition':'unknown'}]

def request(port,body=None):
    req=urllib.request.Request(f'http://127.0.0.1:{port}'+('/health' if body is None else '/v1/chat/completions'),
                              data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=900) as res:return json.load(res)

def new_json(path,data):
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:json.dump(data,f,indent=2);f.write('\n')

def main(a):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',a.port))
    if a.replicates<1 or a.distractors<0:raise ValueError('invalid experiment dimensions')
    root=Path(a.output).resolve();root.mkdir(mode=0o700)
    facts=[{'aliases':[name], 'content':text,'memory_ref':{'namespace':'public-research-fixture','id':name,'revision':'1'}} for name,text in FACTS]
    facts += [{'aliases':[f'distractor{i}'],'content':f'Distractor{i} station access code is {10000+i}.',
               'memory_ref':{'namespace':'public-research-fixture','id':f'distractor{i}','revision':'1'}} for i in range(a.distractors)]
    new_json(root/'fixture.json',{'scope':'public synthetic; no production policy claim','facts':facts})
    new_json(root/'protocol.json',{'tasks':TASKS,'schedule_order':['every-step','preload-only','bounded-refresh'],
        'quality_gate':'no additional incorrect answers vs every-step on identical tasks',
        'cost_gate':'fewer source reads; latency descriptive only at this sample size',
        'promotion':'engineering only; no deployment or general-search claim','max_reads':8,'refresh_interval':4,
        'routing_gate':{'primary_layer':3,'primary_representation':'query-inverse-rotary-f32','primary_pooling':'mean-heads-last-token','partition_budget':1,'min_score':.1,'min_margin':0.,'quality':'match deterministic entity-cue routing on every unique heldout query; exploratory variants cannot replace this gate'},
        'model_config_sha256':hashlib.sha256((Path(a.model)/'config.json').read_bytes()).hexdigest(),
        'runtime_sha256':hashlib.sha256(Path(a.binary).read_bytes()).hexdigest(),
        'model_weight_index_sha256':hashlib.sha256((Path(a.model)/'model.safetensors.index.json').read_bytes()).hexdigest()})
    samples=[];results=[]
    for schedule in ('every-step','preload-only','bounded-refresh'):
        traces=root/schedule;traces.mkdir(mode=0o700)
        command=[a.binary,'serve','--model',a.model,'--placement',a.placement,'--int8',
                 '--image-reader',str(Path(__file__).with_name('fixture_reader.py').resolve()),
                 '--memory-image',str(root),'--read-gateway',str(root/'no-remote.sock'),'--read-authority','public-research',
                 '--trace-dir',str(traces),'--port',str(a.port),'--encoding-cache-mib','256',
                 '--native-schedule',schedule,'--native-refresh-interval','4',
                 '--max-active-records','6','--enable-record-encoding','--enable-memory-diagnostics']
        if schedule=='bounded-refresh':command+=['--native-max-reads','8']
        new_json(root/f'{schedule}-invocation.json',{'argv':command})
        with open(root/f'{schedule}-server.log','xb') as log:
            proc=subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True)
            try:
                deadline=time.monotonic()+900
                while True:
                    if proc.poll() is not None:raise RuntimeError(f'{schedule} server exited {proc.returncode}')
                    try:request(a.port);break
                    except Exception:
                        if time.monotonic()>deadline:raise RuntimeError('model startup timed out')
                        time.sleep(1)
                for replicate in range(a.replicates):
                    for task in TASKS:
                        body={'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':task['query']}],
                              'max_tokens':32,'temperature':0,'memory_encoding_granularity':'record'}
                        response=request(a.port,body);trace_path=traces/f"{response['id']}.json";trace=json.loads(trace_path.read_text())
                        answer=response['choices'][0]['message']['content'].strip().rstrip('.')
                        actual={(f['memory_ref']['namespace'],f['memory_ref']['id'],f['memory_ref']['revision'])
                                for e in trace['recall_events'] for f in e.get('aimee_response',{}).get('facts',[])}
                        expected={('public-research-fixture',id,'1') for id in task['expected']}
                        correct=answer.lower()==task['answer'].lower();selection=expected<=actual
                        if not expected:selection=not actual
                        results.append({'task_id':task['id'],'schedule':schedule,'replicate':replicate,'answer':answer,
                                        'correct':correct,'selection_correct':selection,'source_reads':trace['native_memory_metrics']['source_reads'],
                                        'addressing_attempts':trace['native_memory_metrics']['addressing_attempts'],'elapsed_ms':trace['elapsed_ms']})
                        samples.append({'task_id':task['id'],'replicate':replicate,'trace':str(trace_path.relative_to(root)),
                            'correct':correct,'selection_correct':selection,'condition':{'model':'frozen-int8-'+hashlib.sha256(Path(a.binary).read_bytes()).hexdigest(),
                                'selector':'fixture-exact-cues-attention-spans','schedule':schedule,'archive_records':len(facts),
                                'context_tokens':len(trace['prompt_token_ids']),'position_budget':2048,
                                'cache_state':'process-cold-mixed' if replicate==0 else 'warm-record-cache','encoding_granularity':'record'}})
                        print(json.dumps(results[-1]),flush=True)
                # Collect address features in a separate untimed, memory-free diagnostic pass.
                if schedule=='preload-only':
                    diagnostic=[]
                    for i,task in enumerate(TASKS[:6]):
                        for split,query in [('development',task['query']),('heldout',(f"Please look up {task['partition'].title()} and report its access code." if i%2==0 else f"For {task['partition'].title()} station, which entry number was saved?"))]:
                            body={'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':query}],
                                  'preload_memory':False,'decode_recall':False,'memory_diagnostics':1,'max_tokens':1,'temperature':0}
                            response=request(a.port,body);trace=json.loads((traces/f"{response['id']}.json").read_text())
                            diagnostic.append({'split':split,'family':f'{split}-{i}','partition':task['partition'],'trace_id':response['id'],
                                               'features_by_layer':trace['routing_trace']})
                    new_json(root/'routing-features.json',{'samples':diagnostic})
            finally:
                os.killpg(proc.pid,signal.SIGTERM) if proc.poll() is None else None
                try:proc.wait(timeout=30)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        new_json(root/f'{schedule}-results.json',[r for r in results if r['schedule']==schedule])
    new_json(root/'manifest.json',{'schema':'native-addressing-v1','samples':samples})
    new_json(root/'results.json',results)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for field in ('binary','model','placement','output'):p.add_argument('--'+field,required=True)
    p.add_argument('--port',type=int,default=18943);p.add_argument('--replicates',type=int,default=2)
    p.add_argument('--distractors',type=int,default=1000)
    main(p.parse_args())
