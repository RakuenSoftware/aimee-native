"""Fresh E2B consumer of repaired-pilot records; development evaluation only."""
import datetime,fcntl,hashlib,json,os,random,subprocess,sys,time
from pathlib import Path
from canonical_store import CanonicalStore
from prefix_receiver import PrefixReceiver
from receiver_plan import messages,common_prefix
r=Path(sys.argv[1]);out=Path(sys.argv[2]);assert str(out).startswith('/mnt/pve/backup/aimee-experiments/')
out.mkdir(exist_ok=False)
pilot=r/'acquisition-refinement-development-r1'
while not (pilot/'producer-termination.json').exists():time.sleep(10)
assert (pilot/'completion.json').exists(), 'Acquisition failed; refuse evaluation'
ended=json.loads((pilot/'producer-termination.json').read_text());assert ended['exit_code'] is not None
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
freeze={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'development_only':True,'source':{p.name:sha(p) for p in Path(__file__).parent.glob('*.py')},'records_sha256':sha(pilot/'records.jsonl'),'producer_termination':ended,'family_unit':60,'arms':['None','Native','Text'],'source_session_discarded':True}
(out/'freeze.json').write_text(json.dumps(freeze,indent=2))
lock=open('/opt/jmlr-second-review-20261005/gpu-exclusive.lock','a');fcntl.flock(lock,fcntl.LOCK_EX)
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
owner=CanonicalStore(r/'canonical-store-resumed-ready.json')
accepted={x['family_id']:x for x in map(json.loads,(pilot/'records.jsonl').open())}
with (out/'readbacks.jsonl').open('x') as stream:
    for record in accepted.values():
        value=owner.call('/v1/memory/get',{'method':'memory.get','id':record['canonical_record_id']})
        assert value['status']=='ok' and value['memory']['content']==record['content']
        stream.write(json.dumps(value)+'\n')
receiver=PrefixReceiver(Path('/mnt/pve/backup/aimee-experiments/native-top9-20260930/native-capabilities-20261004/models/gemma'))
assert receiver.sdpa_backend=='math'
training={x['family_id']:x for x in map(json.loads,(r/'fixture/learner/families.jsonl').open())}
families=list(map(json.loads,(r/'fixture/evaluation/families.jsonl').open()));random.Random(20261013).shuffle(families)
counts={a:0 for a in ('None','Native','Text')};n=0
with (out/'responses.jsonl').open('x') as output,(out/'preparations.jsonl').open('x') as preparations:
    for family in families:
        fid=family['family_id'];record=accepted.get(fid);arms=list(counts);random.Random('refinement-'+fid).shuffle(arms)
        for arm in arms:
            selected=None if arm=='None' else record
            plans=[messages(family,item,arm,selected,training[fid]) for item in family['inputs']]
            native=arm=='Native' and selected is not None;prefix=[];key=fid
            if native:
                probes=[messages(family,{'input':p,'slots':{}},arm,selected,training[fid]) for p in ('AAAA probe','ZZZZ probe')]
                prefix=common_prefix([receiver.full_tokens(p) for p in probes])
                prep=receiver.prepare(key,prefix);preparations.write(json.dumps({'family_id':fid,'preparation':prep})+'\n');preparations.flush()
            for item,plan in zip(family['inputs'],plans):
                full=receiver.full_tokens(plan);assert not native or full[:len(prefix)]==prefix
                result=receiver.answer(full[len(prefix):] if native else full,key if native else None)
                score=int(result['output']==item['output']);counts[arm]+=score;n+=1
                output.write(json.dumps({'family_id':fid,'input_id':item['id'],'arm':arm,'score':score,'expected':item['output'],'matching_record_available':record is not None,'canonical_record_id':selected['canonical_record_id'] if selected else None,'process_id':os.getpid(),**result})+'\n');output.flush();os.fsync(output.fileno())
            if native:receiver.retire(key)
        print(json.dumps({'family':fid,'counts':counts,'responses':n}),flush=True)
assert n==3600
(out/'completion.json').write_text(json.dumps({'counts':counts,'inputs_per_arm':1200,'responses':n,'admitted_families':len(accepted),'development_only':True,'fresh_consumer_pid':os.getpid(),'producer_pid':ended['pid'],'all_gpu':True,'sdpa_backend':'math'},indent=2))
