"""Fresh installed Gemma12B None-calibration, after the small receiver queue.

Uses the previously residency-verified serving helper unchanged, stock text
backend, zero CPU offload and no prefix caching. No acquisition or held-out data.
"""
import argparse,datetime,fcntl,hashlib,json,os,subprocess,sys,time,urllib.request
from pathlib import Path
from calibrate import SYSTEM,digest

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);args=p.parse_args();root=args.root
    assert str(root).startswith('/mnt/pve/backup/aimee-experiments/')
    status=root/'calibration-controller-status-r2.json'
    while True:
        value=json.loads(status.read_text())
        if value['state']=='small-receivers-complete':break
        if value['state']=='failed':raise RuntimeError('Earlier calibration failed; do not continue')
        time.sleep(15)
    execution=json.loads((root/'installed-calibration-freeze.json').read_text())
    service_root=root/'installed-calibration-runtime'
    for relative,sha in execution['files'].items():assert digest(service_root/relative)==sha
    lock=open('/opt/jmlr-second-review-20261005/gpu-exclusive.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
    sys.path.insert(0,str(service_root/'source'))
    import run_composition_main as serving
    from transformers import AutoTokenizer
    families=[json.loads(x) for x in (root/'fixture/calibration/families.jsonl').read_text().splitlines()]
    tok=AutoTokenizer.from_pretrained(serving.MODEL,local_files_only=True)
    out=root/'calibration-gemma12b-r1';out.mkdir();block=out/'execution';block.mkdir()
    def body(family,item):
        return {'model':serving.MODEL,'messages':[{'role':'system','content':SYSTEM},
            {'role':'user','content':json.dumps({'language':family['language'],'lexicon':family['lexicon'],
                'input':item['input'],'slots':item['slots']},sort_keys=True)}],
            'temperature':0,'seed':20261011,'max_tokens':64,'stream':False,
            'chat_template_kwargs':{'enable_thinking':False}}
    maximum=max(len(tok.apply_chat_template(body(f,x)['messages'],tokenize=True,add_generation_prompt=True,enable_thinking=False)) for f in families for x in f['inputs'])
    assert maximum+64<=2048
    model_dir=Path(serving.MODEL)
    pins={str(p.relative_to(model_dir)):digest(p) for p in model_dir.rglob('*') if p.is_file() and p.suffix in ('.json','.safetensors','.gguf')}
    (out/'token-preflight.json').write_text(json.dumps({'maximum_tokens':maximum,'cap':64,'model_limit':2048})+'\n')
    service=None
    try:
        service=serving.Service(service_root,block,False)
        proof=serving.physical_summary(service.control({'op':'metrics'}))
        (out/'metadata.json').write_text(json.dumps({'pid':service.process.pid,'start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'checkpoint_files':pins,'runtime_freeze':execution,'residency':proof,'prefix_caching':False,'cpu_offload':0,
            'model_label':'Gemma4-12B','repository_id_verification':'pending release provenance reconciliation'},indent=2)+'\n')
        with (out/'responses.jsonl').open('x') as stream:
            for family in families:
                for item in family['inputs']:
                    payload=body(family,item)
                    request=urllib.request.Request('http://127.0.0.1:18991/v1/chat/completions',data=json.dumps(payload).encode(),
                        headers={'Content-Type':'application/json','Authorization':'Bearer tmlr-local-fixture-only'})
                    start=time.perf_counter()
                    with urllib.request.urlopen(request,timeout=600) as response:value=json.load(response)
                    seconds=time.perf_counter()-start
                    answer=value['choices'][0]['message']['content'].strip()
                    row={'model_id':'google/gemma-4-12B-it','family_id':family['family_id'],'item_id':item['id'],'request':payload,
                         'response':value,'output':answer,'expected':item['output'],'correct':answer==item['output'],
                         'seconds':seconds,'pid':service.process.pid}
                    stream.write(json.dumps(row)+'\n');stream.flush();os.fsync(stream.fileno())
                print(json.dumps({'family_id':family['family_id'],'complete':True}),flush=True)
        after=serving.physical_summary(service.control({'op':'metrics'}))
        assert pins=={str(p.relative_to(model_dir)):digest(p) for p in model_dir.rglob('*') if p.is_file() and p.suffix in ('.json','.safetensors','.gguf')}
        (out/'completion.json').write_text(json.dumps({'passed':True,'responses':480,'weights_unchanged':True,'residency_after':after},indent=2)+'\n')
    finally:
        if service is not None:
            service.stop()
            (out/'process-termination.json').write_text(json.dumps({'pid':service.process.pid,'exit_code':service.process.poll(),
                'end_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})+'\n')

if __name__=='__main__':main()
