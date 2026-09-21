"""Real publisher + Rust reader lifecycle on the complete general KB.

Synthetic SSH override is isolated from the public corpus. No Aimee server is
needed for these named local reads; fixture approvals are publisher-only.
"""
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

p = argparse.ArgumentParser()
p.add_argument('--root', required=True)
p.add_argument('--records', required=True)
p.add_argument('--reader', required=True)
p.add_argument('--issuer', required=True)
p.add_argument('--rust', required=True)
p.add_argument('--reader-gid', type=int, default=-1)
p.add_argument('--reader-user')
a = p.parse_args()
root = Path(a.root)
root.mkdir(mode=0o750)
if a.reader_gid >= 0:
    os.chown(root, -1, a.reader_gid)
private = root/'private'
private.mkdir(mode=0o700)
source = private/'source'
recipient = root/'recipient'
corpus_path = Path(a.records)
original_hash = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
corpus = json.loads(corpus_path.read_text())
rows = corpus['records']
by = {r['id']: r for r in rows}
timings = {}

def cli(*args):
    raw = subprocess.check_output([a.reader, *map(str,args)], text=True)
    return json.loads(raw) if raw else None

def build(name, data):
    path = private/(name+'.json')
    path.write_text(json.dumps(data))
    return cli('build', '--root',source,'--input',path)['view']

def compile_image(name, head, records):
    until=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)).isoformat()
    approval=dict(version=1,id=name,subject='delivery-test',policy_epoch='test',source_view=head,
        active=True,valid_until=until,grants=[],reference_lookups=[dict(namespace=corpus['namespace'],authority='test',mode='exact-key-v1')])
    path=private/(name+'-approval.json')
    path.write_text(json.dumps(dict(authorization=approval,records=records,reads=[])))
    subprocess.run([a.issuer,'--input',str(path),'--key',str(private/'key'),
        '--public-key',str(private/'public'),'--output',str(private/'grant')],check=True,stdout=subprocess.DEVNULL)
    image=private/name
    cli('compile-authorized','--root',source,'--output-root',image,'--authorization',private/'grant',
        '--authority-key',private/'public','--subject','delivery-test','--policy-epoch','test')
    return image

head=build('base',corpus)
cli('publish','--root',source,'--view',head)
image1=compile_image('image1',head,rows)
start=time.perf_counter()
installed1=cli('install-published','--root',image1,'--output-root',recipient,'--reader-gid',a.reader_gid)
timings['initial_install_seconds']=time.perf_counter()-start
args=[a.rust,'read-check','--image-reader',a.reader,'--memory-image',str(recipient),
    '--read-authority','test','--read-gateway',str(root/'NO_GATEWAY.sock')]
if a.reader_user:
    args=['runuser','-u',a.reader_user,'--','env','LD_LIBRARY_PATH='+os.environ.get('LD_LIBRARY_PATH',''),*args]
start=time.perf_counter()
proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,cwd=recipient)
def call(op, **kwargs):
    t=time.perf_counter_ns()
    proc.stdin.write(json.dumps(dict(op=op,**kwargs))+'\n')
    proc.stdin.flush()
    line=proc.stdout.readline()
    assert line,'reader exited'
    return json.loads(line)['result'],(time.perf_counter_ns()-t)/1e6
def read(row):
    r,ms=call('native_search',query='Please provide the reference entry for '+row['key']+'.',limit=4)
    assert len(r.get('facts',[]))==1,r
    f=r['facts'][0]
    assert f['content']==row['content'] and f['memory_ref']=={k:row[k] for k in ['namespace','id','revision']},r
    return ms
try:
    r,_=call('begin');assert 'error' not in r,r
    timings['rust_startup_seconds']=time.perf_counter()-start
    sample=[read(row) for row in random.Random(99317).sample(rows,256)]
    timings['local_read_ms']=dict(median=statistics.median(sample),p95=sorted(sample)[242],mean=statistics.mean(sample))
    for row in rows:read(row)
    changed=dict(by['iana.ssh'],revision='delivery-research-v2',content='RESEARCH OVERRIDE ONLY: IANA service ssh uses TCP port 10443 in this test.')
    removed=by['iana.telnet']
    delta=dict(namespace=corpus['namespace'],kind='general',generation=2,previous=head,
        source='isolated research update, not a public registry assertion',coverage=corpus['coverage'],
        records=[changed],delete=[{k:removed[k] for k in ['namespace','id','revision']}])
    next_head=build('delta',delta)
    cli('publish','--root',source,'--view',next_head,'--expected',head)
    next_rows=[changed if row['id']=='iana.ssh' else row for row in rows if row['id']!='iana.telnet']
    image2=compile_image('image2',next_head,next_rows)
    start=time.perf_counter()
    installed2=cli('install-published','--root',image2,'--output-root',recipient,'--expected',installed1['view'])
    timings['replacement_seconds']=time.perf_counter()-start
    read(by['iana.ssh']) # Existing request remains pinned despite old files unlinked.
    r,ms=call('begin');assert 'error' not in r,r
    timings['new_generation_pin_ms']=ms
    read(changed)
    r,_=call('native_search',query=removed['key'],limit=4)
    assert 'error' in r # Uncovered -> deliberately absent fallback, never stale data.
    for path in recipient.rglob('*'):
        if path.is_file():
            raw=path.read_bytes()
            assert by['iana.ssh']['content'].encode() not in raw
            assert removed['content'].encode() not in raw
    assert len(list((recipient/'snapshots').iterdir()))==1
    start=time.perf_counter()
    withdrawn=cli('withdraw-published','--root',recipient,'--expected',installed2['view'])
    timings['withdrawal_seconds']=time.perf_counter()-start
    r,_=call('begin');assert 'error' in r
    r,_=call('native_search',query=changed['key'],limit=4);assert 'error' in r
    assert not list((recipient/'snapshots').iterdir())
finally:
    proc.stdin.close();proc.wait(timeout=10);proc.stdout.close()
assert hashlib.sha256(corpus_path.read_bytes()).hexdigest()==original_hash
summary=dict(records=len(rows),exhaustive_correct=len(rows),reader_user=a.reader_user,
    timings=timings,initial=installed1,replacement=installed2,withdrawal=withdrawn,
    previous_request_preserved=True,new_request_observed_update=True,retired_record_not_served=True,
    obsolete_payload_bytes_absent=True,withdrawn_reader_blocked=True,withdrawn_snapshot_directories=0,
    gateway_configured=False,public_corpus_sha256=original_hash,
    binary_hashes={name:hashlib.sha256(Path(path).read_bytes()).hexdigest() for name,path in [('rust',a.rust),('reader',a.reader)]})
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
