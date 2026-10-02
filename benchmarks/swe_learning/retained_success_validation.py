"""Revalidate all five prior positive cases with automatic source capture."""
import concurrent.futures
import hashlib
import json
import os
import threading
import time
import urllib.request
import run
import source_learning as source

PUBLICATIONS={}
LOCK=threading.Lock()


def main():
    root=run.ROOT;os.chdir(root)
    manifest=json.loads((root/'manifest.json').read_text())
    assert len(manifest)==5 and len({x['instance_id'] for x in manifest})==5
    assert run.SECONDS==600 and run.STEPS==40 and run.OUTPUT_TOKENS==1536
    state={'status':'running','started':time.time(),'scope':'Selected retained-success regression checks, two native attempts each; historical controls, not a new population effect estimate.','results':[]}
    def save():
        state['updated']=time.time();p=root/'status.next';p.write_text(json.dumps(state,indent=2)+'\n');p.replace(root/'status.json')
    def pipeline(entry):
        origin=root.parent/entry['source_run']
        task=next(t for t in json.loads((origin/'tasks.json').read_text()) if t['instance_id']==entry['instance_id'])
        prior=json.loads((origin/'results'/entry['source_arm']/entry['instance_id']/'result.json').read_text())
        if prior['resolved'] is not True:raise ValueError('declared positive source no longer verified')
        experience=source.capture(task,prior,None,origin)
        with LOCK:
            pub,fact=source.prepare(task,experience,list(PUBLICATIONS.values()))
            PUBLICATIONS[entry['instance_id']]=pub['publication']
            source.write(root/'acquisition'/entry['instance_id']/'publication.json',dict(pub,complete_fact=fact,fact_sha256=hashlib.sha256(fact.encode()).hexdigest()))
        rows=[]
        try:
            for arm in ['retained-native-1','retained-native-2']:
                row=run.attempt(task,arm,pub['publication'])
                if type(row.get('resolved')) is not bool:raise RuntimeError('ungraded retained-success attempt')
                rows.append(row)
                # Preserve the accepted source on either outcome; verify policy.
                previous=experience
                experience=source.capture(task,row,experience)
                if experience!=previous:raise AssertionError('accepted source unexpectedly replaced')
            return {'instance_id':task['instance_id'],'rows':rows}
        finally:
            with LOCK:PUBLICATIONS.pop(entry['instance_id'],None)
    save()
    try:
        run.GRADER={t['instance_id']:t for t in json.loads((root.parent/'selected-grader-only.json').read_text())}
        with urllib.request.urlopen(run.BASE+'/v1/models',timeout=30) as r:run.MODEL=json.load(r)['data'][0]['id']
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(pipeline,e) for e in manifest]
            for future in concurrent.futures.as_completed(futures):
                state['results'].append(future.result());save()
        state['status']='complete'
        state['all_retained']=all(row['resolved'] for result in state['results'] for row in result['rows'])
    except BaseException as error:
        state.update(status='failed',error=repr(error));raise
    finally:save()


if __name__=='__main__':main()
