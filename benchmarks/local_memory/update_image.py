#!/usr/bin/env python3
import argparse,hashlib,json,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--reader',required=True);a=p.parse_args();root=Path(a.root)
for n in [1000,10000,100000,1000000]:
    d=root/str(n);old=json.loads((d/'results.json').read_text())['view'];image=d/'image'
    records=[]
    for i in range(100):
        e=hashlib.sha256(f'entity:{i}'.encode()).hexdigest()[:16]
        records.append({'namespace':'scale','id':str(i),'revision':'2','scope':{'type':'global','value':'_global'},'key':f'device-{e}','content':f'The storage capacity of device-{e} is now 999 GB.','aliases':[f'machine-{e}'],'kind':'fact','tier':'L3','confidence':1,'lifecycle':'active'})
    delta={'namespace':'scale','kind':'general','generation':2,'previous':old,'source':'deterministic-scale-20260920','coverage':['synthetic-facts-and-aliases'],'records':records}
    src=d/'delta.json';src.write_text(json.dumps(delta))
    reader=subprocess.Popen([a.reader,'serve','--root',str(image),'--view',old],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    def call(op):reader.stdin.write(json.dumps(op)+'\n');reader.stdin.flush();return json.loads(reader.stdout.readline())
    call({'op':'pin'})
    result={'count':n,'changed':len(records),'delta_input_bytes':src.stat().st_size}
    start=time.perf_counter();v=json.loads(subprocess.check_output([a.reader,'build','--root',str(image),'--input',str(src)]))['view'];result['build_seconds']=time.perf_counter()-start
    start=time.perf_counter();subprocess.run([a.reader,'publish','--root',str(image),'--view',v,'--expected',old],capture_output=True,check=True);result['publish_seconds']=time.perf_counter()-start
    q=records[0]['key'];before=call({'op':'search','query':q,'limit':1});result['pinned_revision']=before['records'][0]['revision'];reader.terminate();reader.wait()
    start=time.perf_counter();after=json.loads(subprocess.check_output([a.reader,'query','--root',str(image),'--query',q,'--limit','1']));result['new_reader_query_seconds']=time.perf_counter()-start;result['new_revision']=after['records'][0]['revision']
    (d/'update-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
