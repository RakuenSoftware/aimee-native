"""Separate 7-family regression + replay-native diagnostic, no new acquisition claim."""
import datetime,fcntl,hashlib,json,os,subprocess,sys
from pathlib import Path
from prefix_receiver import PrefixReceiver
from receiver_plan import common_prefix,messages
r=Path(sys.argv[1]);out=Path(sys.argv[2]);assert str(out).startswith('/mnt/pve/backup/aimee-experiments/')
out.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
(out/'freeze.json').write_text(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'study':'Previously seen diagnostic data; no prospective learning endpoint','source_hashes':{p.name:sha(p) for p in Path(__file__).parent.glob('*.py')},'family_unit':7,'repetitions':1,'qwen3_06b_excluded':True},indent=2))
lock=open('/opt/jmlr-second-review-20261005/gpu-exclusive.lock','a');fcntl.flock(lock,fcntl.LOCK_EX)
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
model=Path('/mnt/pve/backup/aimee-experiments/native-top9-20260930/native-capabilities-20261004/models/gemma')
receiver=PrefixReceiver(model)
assert receiver.sdpa_backend=='math'
from canonical_store import CanonicalStore
owner=CanonicalStore(r/'canonical-store-resumed-ready.json')
training={x['family_id']:x for x in map(json.loads,(r/'fixture/learner/families.jsonl').open())}
eval={x['family_id']:x for x in map(json.loads,(r/'fixture/evaluation/families.jsonl').open())}
accepted={x['family_id']:x for x in map(json.loads,(r/'records.jsonl').open())}
counts={}
with (out/'responses.jsonl').open('x') as f,(out/'preparations.jsonl').open('x') as preparations,(out/'replay-records.jsonl').open('x') as records:
    for fid,learned in accepted.items():
        family=eval[fid];experience=json.dumps(training[fid]['examples'],sort_keys=True)
        replay=owner.admit({'family_id':fid+'/replay-diagnostic','content':experience,'content_sha256':hashlib.sha256(experience.encode()).hexdigest(),'source_session':'training-experience-replay-diagnostic','record_kind':'experience','not_model_authored_rule':True})
        records.write(json.dumps(replay)+'\n');records.flush()
        for kind in ('Learned','Replay'):
            record=learned if kind=='Learned' else replay
            plans=[messages(family,item,'Text',record,training[fid]) if kind=='Learned' else messages(family,item,'Replay',None,training[fid]) for item in family['inputs']]
            probes=[messages(family,{'input':p,'slots':{}},'Text',record,training[fid]) if kind=='Learned' else messages(family,{'input':p,'slots':{}},'Replay',None,training[fid]) for p in ('AAAA boundary probe','ZZZZ boundary probe')]
            prefix=common_prefix([receiver.full_tokens(p) for p in probes]);key=fid+'/'+kind
            prep=receiver.prepare(key,prefix);preparations.write(json.dumps({'key':key,'preparation':prep,'canonical_record_id':record['canonical_record_id']})+'\n');preparations.flush()
            for item,plan in zip(family['inputs'],plans):
                full=receiver.full_tokens(plan);assert full[:len(prefix)]==prefix
                for arm in ('Text','Native'):
                    ids=full if arm=='Text' else full[len(prefix):]
                    result=receiver.answer(ids,None if arm=='Text' else key)
                    label=kind+'-'+arm;score=int(result['output']==item['output']);counts[label]=counts.get(label,0)+score
                    f.write(json.dumps({'kind':kind,'arm':arm,'family_id':fid,'input_id':item['id'],'expected':item['output'],'score':score,'exact_reconstruction':prefix+full[len(prefix):]==full,'record_id':record['canonical_record_id'],**result})+'\n');f.flush();os.fsync(f.fileno())
            receiver.retire(key)
    (out/'completion.json').write_text(json.dumps({'counts':counts,'inputs_per_arm':140,'scored_campaign':False,'sdpa_backend':'math','all_gpu':True,'pid':os.getpid()},indent=2))
