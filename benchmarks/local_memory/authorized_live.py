#!/usr/bin/env python3
"""Real Aimee reads + real signed audience snapshots/gateways; synthetic grants.
Run only inside the disposable aimee-sparse-scale-20260920 experiment.
No authority writes. This tests enforcement, not a production policy issuer.
"""
import argparse,hashlib,json,os,statistics,subprocess,sys,time
from datetime import datetime,timezone,timedelta
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--src',type=Path,required=True);p.add_argument('--reader',required=True);p.add_argument('--issuer',required=True);p.add_argument('--records',type=int,default=64);a=p.parse_args()
if a.root.exists():raise RuntimeError('fresh evidence directory required')
a.root.mkdir(mode=0o700);sys.path.insert(0,str(a.src))
from aimee_client import AimeeUnixClient,AimeeError
from local_image import AimeeImageClient
from gateway_client import ReadGatewayClient,UnixHTTP
from local_first import LocalFirstClient
project='aimee-sparse-scale-20260920'
volume=subprocess.check_output(['docker','volume','inspect','--format','{{.Mountpoint}}',project+'_aimee-server-home'],text=True).strip()
authority=AimeeUnixClient(volume+'/aimee-http.sock');records=[];reads=[];observations=[]
until=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
# Actual requests to the existing 1M-record isolated Aimee instance.
for i in range(100,100+a.records):
    key='device-'+hashlib.sha256(f'entity:{i}'.encode()).hexdigest()[:16]
    start=time.perf_counter();reply=authority.search(key,4);elapsed=time.perf_counter()-start
    if len(reply['facts'])!=1 or str(reply['facts'][0]['id'])!=str(i):raise RuntimeError('authority fixture mismatch')
    f=reply['facts'][0]
    record={'namespace':'research-authority','id':str(f['id']),'revision':hashlib.sha256(json.dumps(f,sort_keys=True).encode()).hexdigest(),'scope':f['scope'],'key':f['key'],'content':f['content'],'kind':f['kind'],'tier':f['tier'],'confidence':f['confidence'],'lifecycle':'active'}
    records.append(record)
    reads.append({'query':key,'limit':4,'authority':'isolated-aimee','grants':['user:_user'],'valid_until':until,'dependencies':[{k:record[k] for k in ('namespace','id','revision')}],'response':reply})
    observations.append({'phase':'authority_source','query':key,'seconds':elapsed,'ids':[f['id']]})
source=a.root/'authority-only';source.mkdir()
def build(change):
    path=source/'changes.json';path.write_text(json.dumps(change))
    return json.loads(subprocess.check_output([a.reader,'build','--root',str(source),'--input',str(path)]))['view']
base=build({'namespace':'general','kind':'general','generation':1,'records':[],'source':'empty general fixture','coverage':['fixture']})
head=build({'namespace':'research-authority','kind':'server','upstream':base,'generation':1,'records':records,'read_contracts':reads,'source':'actual isolated Aimee read results','coverage':['facts']})
subprocess.run([a.reader,'publish','--root',str(source),'--view',head],check=True)
checks=[];workers=[];clients=[]
try:
    for number in range(2):
        subject=f'model-{number}';home=a.root/subject;home.mkdir(mode=0o700)
        indices=list(range(number*a.records//2,(number+1)*a.records//2))
        subset=[records[i] for i in indices];approved_reads=[reads[i] for i in indices if i%2==0]
        plan={'authorization':{'version':1,'id':subject+'-grant','subject':subject,'policy_epoch':'research-policy-1','source_view':head,'active':True,'valid_until':until,'grants':['user:_user']},'records':subset,'reads':approved_reads}
        planpath=home/'approval-plan.json';planpath.write_text(json.dumps(plan))
        auth=home/'authorization.json';pub=a.root/'authority-public.hex';priv=a.root/'authority-private.key'
        binding=subprocess.check_output([a.issuer,'--input',str(planpath),'--output',str(auth),'--key',str(priv),'--public-key',str(pub)],text=True).strip()
        image=home/'image';flags=['--authorization',str(auth),'--authority-key',str(pub),'--subject',subject,'--policy-epoch','research-policy-1']
        started=time.perf_counter()
        built=json.loads(subprocess.check_output([a.reader,'compile-authorized','--root',str(source),'--output-root',str(image),*flags]))
        observations.append({'phase':'compile','subject':subject,'seconds':time.perf_counter()-started,'view':built['view'],'bytes':sum(x.stat().st_size for x in image.rglob('*') if x.is_file())})
        forbidden=[r['content'].encode() for i,r in enumerate(records) if i not in indices]
        leaked=[str(path.relative_to(image)) for path in image.rglob('*') if path.is_file() and any(secret in path.read_bytes() for secret in forbidden)]
        checks.append({'case':'physical_exclusion','subject':subject,'pass':not leaked,'leaked_paths':leaked})
        local=AimeeImageClient(a.reader,image,authorization=auth,authority_key=pub,subject=subject,policy_epoch='research-policy-1')
        socket=home/'gateway.sock';log=(home/'gateway.log').open('w')
        worker=subprocess.Popen([sys.executable,str(a.src/'read_gateway.py'),'--socket',str(socket),'--upstream-unix',volume+'/aimee-http.sock','--memory-image',str(image),'--image-reader',a.reader,*flags],stdout=log,stderr=log)
        workers.append((worker,log))
        for _ in range(100):
            if socket.exists():break
            if worker.poll() is not None:raise RuntimeError('gateway failed: '+(home/'gateway.log').read_text())
            time.sleep(.05)
        remote=ReadGatewayClient(socket);client=LocalFirstClient(local,remote,'isolated-aimee');clients.append(client)
        for i,request in enumerate(reads):
            start=time.perf_counter();reply=None;error=None
            try:client.begin_request();reply=client.search(request['query'],4)
            except AimeeError as e:error=str(e)
            elapsed=time.perf_counter()-start;allowed=i in indices
            correct=(reply==request['response'] and error is None) if allowed else (reply is None and error is not None)
            observations.append({'phase':'model_read','subject':subject,'index':i,'allowed':allowed,'correct':correct,'seconds':elapsed,'events':client.events,'error':error,'returned_ids':[f['id'] for f in reply['facts']] if reply else []})
        try:
            client.begin_request();client.search('absent-authorized-probe-7f1d992873baf020',4);missing_denied=False
        except AimeeError:missing_denied=True
        checks.append({'case':'missing_has_same_unavailable_outcome','subject':subject,'pass':missing_denied})
        # Model-supplied scope, authorization and writes cannot expand the grant.
        for case,path,body in [('forged_authorization','/search',{'query':reads[0]['query'],'limit':4,'authorization':'forged'}),('scope_escalation','/search',{'query':reads[0]['query'],'limit':4,'authorization':binding,'scope':'all'}),('write_attempt','/v1/memory/store',{'content':'forged'})]:
            connection=UnixHTTP(str(socket),timeout=30);connection.request('POST',path,json.dumps(body),{'Content-Type':'application/json'});r=connection.getresponse();r.read();checks.append({'case':case,'subject':subject,'status':r.status,'pass':r.status in (400,403)});connection.close()
        # Revocation is checked even by an existing client with a pinned view.
        plan['authorization']['active']=False;planpath.write_text(json.dumps(plan))
        subprocess.run([a.issuer,'--input',str(planpath),'--output',str(auth),'--key',str(priv),'--public-key',str(pub)],check=True,stdout=subprocess.DEVNULL)
        try:client.search(reads[indices[0]]['query'],4);revoked=False
        except AimeeError:revoked=True
        checks.append({'case':'live_revocation','subject':subject,'pass':revoked})
        client.close()
finally:
    for client in clients:client.close()
    for worker,log in workers:worker.terminate();worker.wait(timeout=10);log.close()
    authority.close()
    (a.root/'observations.json').write_text(json.dumps(observations,indent=2))
    (a.root/'checks.json').write_text(json.dumps(checks,indent=2))
rows=[r for r in observations if r['phase']=='model_read']
summary={'authority_records':len(records),'model_requests':len(rows),'correct':sum(r['correct'] for r in rows),'checks':checks,'all_pass':all(r['correct'] for r in rows) and all(c['pass'] for c in checks)}
for name,predicate in [('local_hit',lambda r:r['allowed'] and any(not e['remote'] for e in r['events'])),('authorized_fallback',lambda r:r['allowed'] and any(e['remote'] for e in r['events'])),('denied',lambda r:not r['allowed'])]:
    selected=[r for r in rows if predicate(r)];summary[name]={'count':len(selected),'median_ms':statistics.median(r['seconds']*1000 for r in selected)}
(a.root/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
if not summary['all_pass']:raise SystemExit(1)
