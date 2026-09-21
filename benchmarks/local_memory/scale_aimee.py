#!/usr/bin/env python3
"""Isolated deployed Aimee API probe; uses exactly scale_image's canonical facts.
Run only against the named disposable compose project. Bulk fixture loading is
not an ingest benchmark. Unix HTTP excludes network/TLS: external lower bound.
"""
import argparse,hashlib,http.client,json,random,socket,subprocess,time,statistics
from pathlib import Path
PROJECT='aimee-sparse-scale-20260920'
DB=PROJECT+'-aimee-store-db-1'

def sql(statement):
    return subprocess.run(['docker','exec','-i',DB,'sh','-c','PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U postgres -d aimee_store'],input=statement,text=True,capture_output=True,check=True).stdout
class UnixHTTP(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.settimeout(self.timeout);self.sock.connect(self.host)

def run(args):
    root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
    volume=subprocess.check_output(['docker','volume','inspect','--format','{{.Mountpoint}}',PROJECT+'_aimee-server-home'],text=True).strip()
    api=UnixHTTP(volume+'/aimee-http.sock',timeout=120)
    previous=0;rng=random.Random(20260920)
    for n in args.sizes:
        start=time.perf_counter()
        child=subprocess.Popen(['docker','exec','-i',DB,'sh','-c','PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U postgres -d aimee_store'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        child.stdin.write('COPY user_memories (id,kind,tier,key,content,confidence,lifecycle_state) FROM STDIN;\n')
        for i in range(previous,n):
            e=hashlib.sha256(f'entity:{i}'.encode()).hexdigest()[:16]
            content=f'The storage capacity of device-{e} is {256*(1+i%32)} GB. It belongs to project-{i%1000} and uses configuration-{i%127}.'
            child.stdin.write(f'{i}\tfact\tL3\tdevice-{e}\t{content}\t1\tactive\n')
        child.stdin.write('\\.\nANALYZE user_memories;\n');child.stdin.close();child.wait()
        if child.returncode:raise RuntimeError(child.stderr.read())
        meta={'count':n,'load_seconds':time.perf_counter()-start,'transport':'actual Aimee HTTP API over Unix socket; excludes network and TLS','fixture_ingest':'direct COPY canonical facts; no vectors or aliases'}
        indices=rng.sample(range(n),min(100,n));cases=[]
        for i in indices[:args.samples]:
            e=hashlib.sha256(f'entity:{i}'.encode()).hexdigest()[:16]
            for family,q,expected in [('exact',f'device-{e}',str(i)),('natural',f'What is the storage capacity of device-{e}?',str(i)),('missing',f'absent-{e}',None)]:cases.append((family,q,expected))
        for variant in (['default','indexed'] if args.indexed else ['default']):
            if variant=='indexed':
                start=time.perf_counter();sql("CREATE EXTENSION IF NOT EXISTS pg_trgm; CREATE INDEX IF NOT EXISTS bench_key_trgm ON user_memories USING gin(key gin_trgm_ops); CREATE INDEX IF NOT EXISTS bench_content_trgm ON user_memories USING gin(content gin_trgm_ops); CREATE INDEX IF NOT EXISTS bench_fts ON user_memories USING gin(to_tsvector('english',key || ' ' || content)); ANALYZE user_memories;");meta['index_seconds']=time.perf_counter()-start
            samples=[]
            for family,q,expected in cases:
                start=time.perf_counter()
                try:
                    api.request('POST','/v1/memory/search',body=json.dumps({'keywords':[q],'limit':4}),headers={'Content-Type':'application/json'})
                    response=api.getresponse();body=json.loads(response.read());elapsed=time.perf_counter()-start
                    found=[str(r['id']) for r in body.get('facts',[])];error=None if response.status==200 and body.get('status')=='ok' else body
                    row={'family':family,'query':q,'expected':expected,'ids':found,'seconds':elapsed,'error':error,'correct':not error and (expected in found if expected else not found)}
                except Exception as exc:
                    api.close();row={'family':family,'query':q,'seconds':time.perf_counter()-start,'error':type(exc).__name__,'correct':False}
                samples.append(row)
                (root/f'{n}-{variant}-partial.json').write_text(json.dumps(samples,indent=2))
            result=dict(meta,variant=variant,samples=samples); result['summary']={}
            for family in ['exact','natural','missing']:
                rows=[r for r in samples if r['family']==family];ts=sorted(r['seconds']*1000 for r in rows)
                result['summary'][family]={'count':len(rows),'correct':sum(bool(r['correct']) for r in rows),'errors':sum(bool(r['error']) for r in rows),'median_ms':statistics.median(ts),'max_ms':max(ts)}
            (root/f'{n}-{variant}.json').write_text(json.dumps(result,indent=2));print(json.dumps({'count':n,'variant':variant,'summary':result['summary']}),flush=True)
            if variant=='indexed':sql('DROP INDEX bench_key_trgm; DROP INDEX bench_content_trgm; DROP INDEX bench_fts;')
        previous=n

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--sizes',nargs='+',type=int,default=[1000,10000,100000,1000000]);p.add_argument('--samples',type=int,default=10);p.add_argument('--indexed',action='store_true');run(p.parse_args())
