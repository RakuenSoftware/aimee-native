#!/usr/bin/env python3
"""Reproducible real image-reader scale probe. No model or remote equivalence claim."""
import argparse, hashlib, json, os, random, statistics, subprocess, time
from pathlib import Path

def run(args):
    root=Path(args.output); root.mkdir(parents=True,exist_ok=True)
    rng=random.Random(20260920)
    for n in args.sizes:
        directory=root/str(n); directory.mkdir(exist_ok=True)
        source=directory/'source.json'; image=directory/'image'
        start=time.perf_counter()
        with source.open('w') as f:
            f.write('{"namespace":"scale","kind":"general","generation":1,"source":"deterministic-scale-20260920","coverage":["synthetic-facts-and-aliases"],"records":[')
            for i in range(n):
                entity=hashlib.sha256(f'entity:{i}'.encode()).hexdigest()[:16]
                record={'namespace':'scale','id':str(i),'revision':'1','scope':{'type':'global','value':'_global'},'key':f'device-{entity}',
                  'content':f'The storage capacity of device-{entity} is {256*(1+i%32)} GB. It belongs to project-{i%1000} and uses configuration-{i%127}.',
                  'aliases':[f'machine-{entity}'],'kind':'fact','tier':'L3','confidence':1,'lifecycle':'active'}
                if i: f.write(',')
                f.write(json.dumps(record,separators=(',',':')))
            f.write(']}')
        meta={'count':n,'source_bytes':source.stat().st_size,'source_sha256':hashlib.file_digest(source.open('rb'),'sha256').hexdigest(),'generate_seconds':time.perf_counter()-start}
        start=time.perf_counter()
        built=subprocess.run(['/usr/bin/time','-v','-o',str(directory/'build-resource.txt'),args.reader,'build','--root',str(image),'--input',str(source)],capture_output=True,text=True)
        meta['build_seconds']=time.perf_counter()-start
        if built.returncode:
            meta['build_error']=built.stderr; (directory/'results.json').write_text(json.dumps(meta,indent=2)); continue
        view=json.loads(built.stdout)['view'];meta['view']=view
        subprocess.run([args.reader,'publish','--root',str(image),'--view',view],check=True,capture_output=True)
        meta['image_bytes']=sum(p.stat().st_size for p in image.rglob('*') if p.is_file())
        start=time.perf_counter()
        p=subprocess.Popen([args.reader,'serve','--root',str(image)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        def call(request):
            p.stdin.write(json.dumps(request)+'\n');p.stdin.flush();return json.loads(p.stdout.readline())
        call({'op':'pin'});meta['reader_start_seconds']=time.perf_counter()-start
        meta['reader_status']=Path(f'/proc/{p.pid}/status').read_text()
        samples=[]
        ids=rng.sample(range(n),min(100,n))
        cases=[]
        for i in ids:
            entity=hashlib.sha256(f'entity:{i}'.encode()).hexdigest()[:16]
            for family,q,expected in [('exact',f'device-{entity}',str(i)),('natural',f'What is the storage capacity of device-{entity}?',str(i)),('alias',f'machine-{entity}',str(i)),('missing',f'absent-{entity}',None)]:
                cases.append((family,q,expected))
        rng.shuffle(cases)
        for family,q,expected in cases:
            start=time.perf_counter(); result=call({'op':'search','query':q,'limit':4}); elapsed=time.perf_counter()-start
            ids_found=[r['id'] for r in result.get('records',[])]; error=result.get('error')
            samples.append({'family':family,'query':q,'expected':expected,'ids':ids_found,'seconds':elapsed,'error':error,'correct':not error and (expected in ids_found if expected else not ids_found),'reader_us':result.get('elapsed_us'),'candidates':result.get('candidates'),'bytes_read':result.get('bytes_read')})
        p.terminate();p.wait()
        meta['samples']=samples;meta['summary']={}
        for family in ['exact','natural','alias','missing']:
            rows=[s for s in samples if s['family']==family];times=sorted(s['seconds']*1000 for s in rows)
            meta['summary'][family]={'count':len(rows),'correct':sum(s['correct'] for s in rows),'errors':sum(bool(s['error']) for s in rows),'median_ms':statistics.median(times),'p95_ms':times[int(.95*(len(times)-1))]}
        (directory/'results.json').write_text(json.dumps(meta,indent=2)+'\n')
        print(json.dumps({k:meta[k] for k in ['count','build_seconds','reader_start_seconds','image_bytes','summary']}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reader',required=True);p.add_argument('--output',required=True);p.add_argument('--sizes',nargs='+',type=int,default=[1000,10000,100000,1000000]);run(p.parse_args())
