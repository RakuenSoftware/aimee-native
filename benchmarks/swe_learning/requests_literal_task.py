"""Full-agent follow-up to Requests procedure fidelity; grading stays external."""
import concurrent.futures
import hashlib
import json
import os
import pathlib
import time
import urllib.request
import run
import source_learning as source


def main():
    root=run.ROOT
    os.chdir(root)
    fixture=json.loads((root/'fixture.json').read_text())
    task=fixture['task']
    assert task['instance_id']=='psf__requests-2193'
    assert run.SECONDS==600 and run.STEPS==40 and run.OUTPUT_TOKENS==1536
    state={'status':'acquiring_source','started':time.time(),'scope':'Post-hoc full-agent regression validation on Requests 2193. Three matched delivery conditions; not a population effect estimate.','results':{}}
    def save():
        state['updated']=time.time()
        p=root/'status.next';p.write_text(json.dumps(state,indent=2)+'\n');p.replace(root/'status.json')
    save()
    try:
        with urllib.request.urlopen(run.BASE+'/v1/models',timeout=30) as r:run.MODEL=json.load(r)['data'][0]['id']
        run.GRADER={t['instance_id']:t for t in json.loads((root.parent/'selected-grader-only.json').read_text())}
        previous=root.parent/'broader-source-learning-20260928'
        row=json.loads((previous/'results/source-control'/task['instance_id']/'result.json').read_text())
        assert row['resolved'] is True
        assert hashlib.sha256(row['model_patch'].encode()).hexdigest()==fixture['source_patch_sha256']
        experience=source.capture(task,row,None,previous)
        pub,fact=source.prepare(task,experience,[])
        assert fact==fixture['compact_fact'], 'automatic acquisition differs from declared literal procedure'
        assert pub['publication']==fixture['expected_publications']['compact']
        source.write(root/'acquired-publication.json',dict(pub,complete_fact=fact))
        state.update(status='running',publication=pub['publication']);save()
        # Independent clean checkouts; each retained result is officially graded.
        # Two pipelines overlap CPU grading with generation; no new source facts.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures={pool.submit(run.attempt,task,arm,p,t):arm for arm,p,t in [
                ('literal-native',pub['publication'],None),
                ('literal-text',None,fact),('literal-control',None,None)]}
            for future in concurrent.futures.as_completed(futures):
                row=future.result();state['results'][futures[future]]=row
                if type(row.get('resolved')) is not bool:raise RuntimeError('ungraded attempt: '+futures[future])
                save()
        state['status']='complete'
    except BaseException as error:
        state.update(status='failed',error=repr(error));raise
    finally:save()


if __name__=='__main__':main()
