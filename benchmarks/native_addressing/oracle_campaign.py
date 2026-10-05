"""Independent oracle-selected native-consumption control; never trains routing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
from campaign import TASKS,SYSTEM,FACTS,new_json,request


def main(a):
    with socket.socket() as probe:probe.bind(('127.0.0.1',a.port))
    root=Path(a.output).resolve();root.mkdir(mode=0o700)
    facts=[{'aliases':[name],'content':text,'memory_ref':{'namespace':'public-research-fixture','id':name,'revision':'1'}} for name,text in FACTS]
    new_json(root/'fixture.json',{'scope':'public synthetic oracle consumption control','facts':facts})
    traces=root/'traces';traces.mkdir(mode=0o700)
    command=[a.binary,'serve','--model',a.model,'--placement',a.placement,'--int8',
        '--image-reader',str(Path(__file__).with_name('fixture_reader.py').resolve()),'--memory-image',str(root),
        '--read-gateway',str(root/'no-remote.sock'),'--read-authority','public-research','--trace-dir',str(traces),
        '--port',str(a.port),'--encoding-cache-mib','256','--native-schedule','preload-only','--max-active-records','6','--enable-record-encoding']
    new_json(root/'protocol.json',{'scope':__doc__,'argv':command,'tasks':TASKS,'predeclared_gate':'all revision-bound expected records discovered; exact answer separately scored',
                                 'runtime_sha256':hashlib.sha256(Path(a.binary).read_bytes()).hexdigest()})
    rows=[]
    with open(root/'server.log','xb') as log:
        proc=subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True)
        try:
            deadline=time.monotonic()+900
            while True:
                if proc.poll() is not None:raise RuntimeError('oracle server exited')
                try:request(a.port);break
                except Exception:
                    if time.monotonic()>deadline:raise RuntimeError('startup timeout')
                    time.sleep(1)
            for enabled in (False,True):
                for task in TASKS:
                    # Research owner supplies sealed oracle IDs to the read fixture,
                    # independently of the model prompt and hidden-state features.
                    hint=root/'oracle-hint.json';temp=root/'oracle-hint-next.json'
                    new_json(temp,{'ids':task['expected']});temp.replace(hint)
                    body={'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':task['query']}],
                          'max_tokens':32,'temperature':0,'aimee_memory':enabled,'memory_encoding_granularity':'record'}
                    response=request(a.port,body);answer=response['choices'][0]['message']['content'].strip().rstrip('.')
                    trace=json.loads((traces/f"{response['id']}.json").read_text())
                    actual={f['memory_ref']['id'] for e in trace['recall_events'] or [] for f in e.get('aimee_response',{}).get('facts',[])}
                    row={'task_id':task['id'],'native_enabled':enabled,'answer':answer,'correct':answer.lower()==task['answer'].lower(),
                         'selection_correct':actual==set(task['expected']) if enabled else None,'trace':response['id'],'elapsed_ms':trace['elapsed_ms']}
                    rows.append(row);print(json.dumps(row),flush=True)
        finally:
            if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=30)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
    new_json(root/'results.json',rows)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for field in ('binary','model','placement','output'):p.add_argument('--'+field,required=True)
    p.add_argument('--port',type=int,default=18943)
    main(p.parse_args())
