"""Five-round bundled experience study. Private experimental orchestration."""
import hashlib,json,random,subprocess,sys
from pathlib import Path
from procedure_gate import validate
repo=Path(__file__).resolve().parents[2]
def read(p):return json.loads(p.read_text())
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def save(p,x):p.write_text(json.dumps(x,indent=2))
mode=sys.argv[1];root=Path(sys.argv[2])
if mode=='init':
 old=Path(sys.argv[3]);root.mkdir();root.chmod(0o755)
 workflows=read(old/'workflows.json');rng=random.Random(2026092304);evaluation=[]
 for i,w in enumerate(workflows):
  w['name']=f'Birch{i:03d}';w['key']=f'procedure for workflow {w["name"]}'
  w['heldout_inputs']=rng.sample(list(range(200,400)),20)
  for x in w['heldout_inputs']:
   evaluation.append(dict(id=f'task-{w["name"]}-{x}',workflow=w['name'],key=w['key'],input=x,domain='affine-procedure',source='fresh-experience',query=f'Execute my private workflow {w["name"]} on input {x}. Return only the integer result. If the procedure is unknown, return unknown.',expected=str(w['multiplier']*x+w['offset']),scorer='integer'))
 rng.shuffle(evaluation);save(root/'workflows.json',workflows);save(root/'evaluation.json',evaluation)
 (root/'image').symlink_to((old/'image').resolve(),target_is_directory=True)
 save(root/'protocol.json',dict(seed=2026092304,rounds=5,workflows=24,evaluation_inputs='200..399, disjoint from all training inputs',training_inputs=[1,4,9,2,3,5,6],evaluation_sha256=hashlib.sha256((root/'evaluation.json').read_bytes()).hexdigest(),interpretation='Bundled intervention; same task functions with new identities and new evaluation inputs; not five independent replications. Evaluation outcomes withheld from learning.'))
elif mode=='prepare':
 n=int(sys.argv[3]);out=root/f'r{n}-plan';out.mkdir();out.chmod(0o755);(out/'image').symlink_to((root/'image').resolve(),target_is_directory=True)
 workflows=read(root/'workflows.json');prior=read(root/f'r{n-1}-source/selected-procedures.json') if n>1 else {w['key']:'unknown' for w in workflows}
 events=[]
 for j in range(1,n):events+=read(root/f'r{j}-decisions.json')
 # Persist compact success/failure observations through real Aimee memory storage.
 assertions=[]
 for j,e in enumerate(events):
  for producer in ['gemma','qwen']:
   v=e[producer+'_validation'];bad=next((c for c in v['checks'] if c['actual']!=c['expected']),None)
   detail=f"fails input {bad['input']}: predicted {bad['actual']}, observed {bad['expected']}" if bad else ('passes all observed examples' if v['accepted'] else 'has unsupported syntax')
   key=f'experience Birch round {e["round"]} {e["workflow"]} {producer}'
   # Retain exact candidate separately; compact authoritative observation is user assertion.
   assertions.append(dict(key=key,text=f'My {key} is {detail}.'))
 memory={}
 if assertions:
  with (out/'memory-ingestion.jsonl').open('x') as log:
   subprocess.run([str(repo/'.local/bin/scale-ingest'),str(out/'memory-export.json')],input=''.join(json.dumps(a)+'\n' for a in assertions),text=True,stdout=log,check=True)
  memory={r['key']:r['content'] for r in read(out/'memory-export.json') if r['key'] in {a['key'] for a in assertions}}
  assert len(memory)==len(assertions)
 save(out/'retained-experience.json',memory)
 cases=[];successes=[]
 for w in workflows:
  examples=[dict(input=x,output=w['multiplier']*x+w['offset']) for x in [1,4,9]]
  if validate(prior[w['key']],examples)['accepted']:successes.append(dict(workflow=w['name'],examples=examples,validated_rule=prior[w['key']]))
 for w in workflows:
  base=[1,4,9];original=[dict(input=x,output=w['multiplier']*x+w['offset']) for x in base]
  # More observations are requested only for currently unresolved procedures.
  additions=[2,3,5,6][:n-1] if not validate(prior[w['key']],original)['accepted'] else []
  examples=[dict(input=x,output=w['multiplier']*x+w['offset']) for x in base+additions]
  history=[dict(round=e['round'],gemma=e['gemma'],qwen=e['qwen'],feedback={k:v for k,v in memory.items() if w['name'] in k and f"round {e['round']} " in k}) for e in events if e['workflow']==w['name']]
  exemplar=next((s for s in successes if s['workflow']!=w['name']),None)
  query='Learn the integer transformation for private workflow '+w['name']+'. Observed training examples: '+json.dumps(examples)+'. Previous accepted rule: '+prior[w['key']]+'. Retained attempts and executor evidence: '+json.dumps(history)+'. Validated lesson from a different workflow (its coefficients are not this workflow\'s answer): '+json.dumps(exemplar)+'. Infer and check your own reusable arithmetic rule. Return only one sentence under 100 characters: Multiply the input by A and add B (or subtract B).'
  cases.append(dict(id='learn-'+w['name'],workflow=w['name'],key=w['key'],domain='affine-procedure',source='experience-learning',query=query,examples=examples,expected='not scored as a task answer',scorer='text'))
 save(out/'cases.json',cases);(out/'heldout.json').write_bytes((root/'evaluation.json').read_bytes());save(out/'plan.json',dict(round=n,training_only=True,retains_all_prior_candidates=True))
elif mode=='select':
 n=int(sys.argv[3]);plan=root/f'r{n}-plan';g=rows(root/f'r{n}-gemma-training/results.jsonl');q=rows(root/f'r{n}-qwen-training/results.jsonl');assert len(g)==len(q)==24
 qb={r['case_spec']['key']:r for r in q};prior=read(root/f'r{n-1}-source/selected-procedures.json') if n>1 else {r['case_spec']['key']:'unknown' for r in g}
 decisions=[];out=root/f'r{n}-selected';out.mkdir();selected=[]
 for r in g:
  c=r['case_spec'];donor=qb[c['key']];gv=validate(r['answer'],c['examples']);qv=validate(donor['answer'],c['examples'])
  chosen=r['answer'] if gv['accepted'] else donor['answer'] if qv['accepted'] else prior[c['key']]
  producer='gemma' if gv['accepted'] else 'qwen' if qv['accepted'] else 'retained'
  decisions.append(dict(round=n,workflow=c['workflow'],key=c['key'],gemma=r['answer'],qwen=donor['answer'],gemma_validation=gv,qwen_validation=qv,selected=chosen,producer=producer))
  # Publication input is an explicitly derived selection, not a fabricated model response.
  selected.append(dict(case_spec=c,enabled=False,answer=chosen,selection_provenance=dict(producer=producer,gemma=str(root/f'r{n}-gemma-training/results.jsonl'),qwen=str(root/f'r{n}-qwen-training/results.jsonl'))))
 save(root/f'r{n}-decisions.json',decisions);(out/'results.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in selected));(out/'DONE').write_text('derived validated selection; not inference')
else:raise ValueError(mode)
