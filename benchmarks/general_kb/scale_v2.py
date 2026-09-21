"""Measure actual compiled local retrieval at 13K, 100K and full v2 size."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import time

p=argparse.ArgumentParser()
p.add_argument('--base',required=True);p.add_argument('--expanded',required=True)
p.add_argument('--root',required=True);p.add_argument('--reader',required=True)
p.add_argument('--issuer',required=True);p.add_argument('--rust',required=True)
p.add_argument('--cases',required=True)
a=p.parse_args()
root=Path(a.root);root.mkdir(exist_ok=True,mode=0o750);os.chown(root,0,989)
base=json.loads(Path(a.base).read_text());expanded=json.loads(Path(a.expanded).read_text())
extra=[r for r in expanded['records'] if r['id'].startswith('geonames.')]
random.Random(82026).shuffle(extra)
cases=json.loads(Path(a.cases).read_text())

def cli(*args):
    raw=subprocess.check_output([a.reader,*map(str,args)],text=True)
    return json.loads(raw) if raw else None

def stats(values):
    values=sorted(values)
    return dict(median=statistics.median(values),p95=values[int(.95*len(values))-1],mean=statistics.mean(values))

def memory(pid):
    out=[]
    def visit(pid):
        try:
            fields={k:v.strip() for k,v in (line.split(':',1) for line in Path(f'/proc/{pid}/status').read_text().splitlines() if ':' in line)}
            out.append({k:fields.get(k) for k in ['Name','VmRSS','VmHWM']})
            for child in Path(f'/proc/{pid}/task/{pid}/children').read_text().split():visit(child)
        except FileNotFoundError:pass
    visit(pid)
    return out

for count in [len(base['records']),100000,len(expanded['records'])]:
    run=root/str(count);summary_path=run/'summary.json'
    if summary_path.exists():print('already complete',count,flush=True);continue
    run.mkdir(mode=0o750);os.chown(run,0,989)
    private=run/'private';private.mkdir(mode=0o700)
    rows=base['records']+extra[:count-len(base['records'])]
    rows.sort(key=lambda r:r['id'])
    changes=dict(base,records=rows,source='Scale study of pinned public general-v2 corpus')
    source=private/'source';input_path=private/'input.json'
    input_path.write_text(json.dumps(changes,ensure_ascii=False,separators=(',',':')))
    start=time.perf_counter()
    head=cli('build','--root',source,'--input',input_path)['view']
    cli('publish','--root',source,'--view',head)
    source_seconds=time.perf_counter()-start
    print(json.dumps(dict(records=count,stage='source_built',seconds=source_seconds)),flush=True)
    until=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=4)).isoformat()
    grant=dict(version=1,id='public-scale-'+str(count),subject='scale',policy_epoch='test',source_view=head,
        active=True,valid_until=until,grants=[],reference_lookups=[dict(namespace=base['namespace'],authority='test',mode='exact-key-v1')])
    plan=private/'plan.json';plan.write_text(json.dumps(dict(authorization=grant,records=rows,reads=[]),ensure_ascii=False,separators=(',',':')))
    subprocess.run([a.issuer,'--input',str(plan),'--key',str(private/'key'),'--public-key',str(private/'public'),
        '--output',str(private/'grant')],check=True,stdout=subprocess.DEVNULL)
    start=time.perf_counter()
    cli('compile-authorized','--root',source,'--output-root',run/'image','--authorization',private/'grant',
        '--authority-key',private/'public','--subject','scale','--policy-epoch','test')
    compile_seconds=time.perf_counter()-start
    for d,dirs,files in os.walk(run/'image'):
        os.chown(d,0,989);os.chmod(d,0o750)
        for name in files:
            f=Path(d)/name;os.chown(f,0,989);os.chmod(f,0o640)
    print(json.dumps(dict(records=count,stage='compiled',seconds=compile_seconds)),flush=True)
    args=['runuser','-u','aimee-auth-native','--','env','LD_LIBRARY_PATH='+os.environ.get('LD_LIBRARY_PATH',''),a.rust,
        'read-check','--memory-image',str(run/'image'),'--image-reader',a.reader,'--read-authority','test',
        '--read-gateway',str(run/'NO_GATEWAY.sock')]
    start=time.perf_counter();proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,cwd=run)
    def call(op,query=None):
        t=time.perf_counter_ns();q=dict(op=op)
        if query is not None:q.update(query=query,limit=4)
        proc.stdin.write(json.dumps(q)+'\n');proc.stdin.flush()
        raw=proc.stdout.readline();assert raw,'reader exited'
        return json.loads(raw)['result'],(time.perf_counter_ns()-t)/1e6
    def read(row):
        answer,ms=call('native_search','Please provide the reference entry for '+row['key']+'.')
        facts=answer.get('facts',[])
        ok=len(facts)==1 and facts[0]['content']==row['content'] and facts[0]['memory_ref']=={k:row[k] for k in ['namespace','id','revision']}
        return ok,ms,answer
    failures=[]
    try:
        r,_=call('begin');assert 'error' not in r,r
        startup=time.perf_counter()-start
        print(json.dumps(dict(records=count,stage='reader_ready',seconds=startup)),flush=True)
        old_times=[]
        for row in random.Random(99317).sample(base['records'],256):
            ok,ms,answer=read(row);assert ok,answer;old_times.append(ms)
        new_times=[]
        for row in random.Random(2310).sample(rows,min(len(rows),512)):
            ok,ms,answer=read(row);assert ok,answer;new_times.append(ms)
        named_correct=0
        for case in cases:
            answer,_=call('native_search',case['query'])
            got={f['memory_ref']['id'] for f in answer.get('facts',[])}
            assert got==set(case['memory_ids']),(case['id'],answer)
            named_correct+=1
        # Multiple distinct entries, no oracle query contracts stored in the KB.
        pairs=random.Random(1919).sample(rows,200)
        for left,right in zip(pairs[::2],pairs[1::2]):
            answer,_=call('native_search',left['key']+' and '+right['key'])
            assert {f['memory_ref']['id'] for f in answer.get('facts',[])}=={left['id'],right['id']},answer
        for i in range(100):
            answer,_=call('native_search',f'place definitely-nonexistent-{i} ZZ 999999999999')
            assert 'error' in answer # miss attempts absent fallback; never a guessed local fact
        for index,row in enumerate(rows):
            ok,ms,answer=read(row)
            if not ok:failures.append(dict(id=row['id'],answer=answer))
            if index and index%50000==0:print(json.dumps(dict(records=count,stage='exhaustive',done=index)),flush=True)
        usage=memory(proc.pid)
    finally:
        proc.stdin.close();proc.wait(timeout=10);proc.stdout.close()
    summary=dict(records=count,source_build_seconds=source_seconds,compile_seconds=compile_seconds,
        startup_seconds=startup,image_bytes=sum(p.stat().st_size for p in (run/'image').rglob('*') if p.is_file()),
        original_256_query_ms=stats(old_times),mixed_512_query_ms=stats(new_times),
        original_query_sets_correct=named_correct,multi_record_queries_correct=100,misses_correct=100,
        exhaustive_correct=count-len(failures),failures=failures,process_memory=usage,
        scope='exact named address retrieval, no semantic aliases, no Qwen answer generation',
        binary_hashes={n:hashlib.sha256(Path(path).read_bytes()).hexdigest() for n,path in [('rust',a.rust),('reader',a.reader)]})
    summary_path.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
summaries=[json.loads((root/str(n)/'summary.json').read_text()) for n in [len(base['records']),100000,len(expanded['records'])]]
(root/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
