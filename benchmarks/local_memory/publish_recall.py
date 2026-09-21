#!/usr/bin/env python3
"""Control-plane research publisher. Never run in the model reader identity.
Reads Aimee's real search responses and publishes exact-request reuse contracts.
Expiry is an operator-controlled research bound, not a lease claimed from the
current Aimee API. Production use needs authority mutation/invalidation wiring.
"""
import argparse,hashlib,json,subprocess,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'integrations/qwen_aimee'))
from aimee_client import AimeeClient

p=argparse.ArgumentParser();p.add_argument('--reader',required=True);p.add_argument('--root',required=True);p.add_argument('--queries',required=True);p.add_argument('--upstream',required=True);p.add_argument('--authority',required=True);p.add_argument('--config',required=True);p.add_argument('--ca',required=True);p.add_argument('--cert',required=True);p.add_argument('--key',required=True);p.add_argument('--generation',type=int,default=1);p.add_argument('--previous',default='');p.add_argument('--valid-seconds',type=int,default=3600);p.add_argument('--limit',type=int,default=2);p.add_argument('--namespace',default='aimee-published');a=p.parse_args()
if not 0<a.valid_seconds<=3600:raise ValueError('research publication expiry must be 1..3600 seconds')
client=AimeeClient(a.config,a.ca,cert_file=a.cert,key_file=a.key,keepalive=True)
records={};contracts=[];until=(datetime.now(timezone.utc)+timedelta(seconds=a.valid_seconds)).isoformat()
for query in dict.fromkeys(json.loads(Path(a.queries).read_text())):
    reply=client.search(query,a.limit)
    if not reply['facts'] or reply.get('windows'):continue
    dependencies=[]
    for f in reply['facts']:
        ref={'namespace':a.namespace,'id':str(f['id']),'revision':hashlib.sha256(json.dumps(f,sort_keys=True).encode()).hexdigest()}
        record={**ref,'scope':{'type':'user','value':'_user'},'key':f.get('key',str(f['id'])),'content':f['content'],'kind':f.get('kind','fact'),'tier':f.get('tier','L3'),'confidence':f.get('confidence',1),'lifecycle':'active','metadata':{'aimee_response_fact':f}}
        if ref['id'] in records and records[ref['id']]!=record:raise RuntimeError('source changed during publication; retry from a coherent authority snapshot')
        records[ref['id']]=record;dependencies.append(ref)
    contracts.append({'query':query,'limit':a.limit,'authority':a.authority,'grants':['user:_user'],'valid_until':until,'dependencies':dependencies,'response':reply})
client.close()
changes={'namespace':a.namespace,'kind':'server','generation':a.generation,'upstream':a.upstream,'previous':a.previous,'records':list(records.values()),'read_contracts':contracts,'source':'Aimee search responses; operator-authorized bounded research replay','coverage':['published_exact_request_responses','source_fact_content','scope','expiry']}
root=Path(a.root);root.mkdir(parents=True,exist_ok=True);src=root.parent/'publication.json';src.write_text(json.dumps(changes,indent=2))
view=json.loads(subprocess.check_output([a.reader,'build','--root',a.root,'--input',str(src)]))['view']
cmd=[a.reader,'publish','--root',a.root,'--view',view]
if a.previous:cmd+=['--expected',a.previous]
subprocess.run(cmd,check=True)
print(json.dumps({'view':view,'contracts':len(contracts),'records':len(records),'valid_until':until}))
