"""Wait for scored phases, audit primary shards, then analyze complete coverage.

CPU aggregation waits until context timings finish, avoiding host contention.
Never relaunches inference or replaces a scored output.
"""
import argparse,datetime,hashlib,json,os,subprocess,time
from pathlib import Path

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--execution-freeze',type=Path,required=True)
    args=p.parse_args();r=args.root;source=Path(__file__).parent
    assert str(r).startswith('/mnt/pve/backup/aimee-experiments/')
    freeze=json.loads(args.execution_freeze.read_text())
    for name,digest in freeze['files'].items():assert sha(source/name)==digest
    def report(state,**fields):
        tmp=r/'analysis-status-r1.tmp'
        tmp.write_text(json.dumps(dict(state=state,pid=os.getpid(),utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),**fields),indent=2))
        tmp.replace(r/'analysis-status-r1.json')
    try:
        report('waiting-for-scored-phases')
        while True:
            statuses=[json.loads((r/name).read_text()) for name in ('installed-retention-status-r2.json','context-growth-status-r1.json')]
            if any(x['state']=='failed' for x in statuses):raise RuntimeError({'scored_phase_failed':statuses})
            if all(x['state']=='complete' for x in statuses):break
            time.sleep(30)
        report('merging-complete-primary-shards')
        manifest=[];count=0;tmp=r/'responses-merge-r1.jsonl.partial'
        assert not (r/'responses.jsonl').exists(),'Refuse to replace existing scored-response aggregate'
        with tmp.open('xb') as output:
            for name in ('gemma12b','gemma-e2b','qwen3','qwen35'):
                for repeat in (1,2,3):
                    run=r/('receiver-'+name+'-r'+str(repeat))
                    complete=json.loads((run/'completion.json').read_text())
                    assert complete['passed'] and complete['weights_unchanged'] and complete['responses']==8400
                    shard=run/'responses.jsonl';n=0;h=hashlib.sha256()
                    with shard.open('rb') as f:
                        for line in f:
                            assert line.endswith(b'\n');h.update(line);output.write(line);n+=1
                    assert n==8400;count+=n
                    manifest.append({'file':str(shard.relative_to(r)),'responses':n,'sha256':h.hexdigest(),'completion_sha256':sha(run/'completion.json')})
            output.flush();os.fsync(output.fileno())
        assert count==100800;tmp.rename(r/'responses.jsonl')
        with (r/'response-aggregation-manifest-r1.json').open('x') as f:
            json.dump({'passed':True,'responses':count,'shards':manifest,'combined_sha256':sha(r/'responses.jsonl'),'analysis_freeze':freeze},f,indent=2)
        report('family-unit-analysis')
        subprocess.run(['/opt/aimee-native-serving/clean-release-env-build2/bin/python',str(source/'analyze.py'),str(r)],check=True)
        report('complete',responses=count,families=60,acquired_families=7)
    except BaseException as exc:
        report('failed',error=repr(exc));raise

if __name__=='__main__':main()
