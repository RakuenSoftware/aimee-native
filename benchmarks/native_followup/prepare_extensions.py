"""Frozen extension fixtures: seed replication, structured transformations, ablations."""
import itertools,json,random,re,sys
from pathlib import Path
from procedure_gate import validate
mode=sys.argv[1];root=Path(sys.argv[2])
def save(p,x):p.write_text(json.dumps(x,indent=2))
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
if mode=='seed':
 seed=int(sys.argv[3]);image=Path(sys.argv[4]);root.mkdir();root.chmod(0o755);(root/'image').symlink_to(image.resolve(),target_is_directory=True)
 rng=random.Random(seed);params=rng.sample(list(itertools.product(range(2,10),range(1,20))),24)
 save(root/'workflows.json',[dict(name=f'Seed{seed}-{i}',key=f'procedure {i}',multiplier=a,offset=b) for i,(a,b) in enumerate(params)])
 save(root/'seed.json',dict(seed=seed,parameters_frozen_before_inference=True))
elif mode=='structured':
 seed=int(sys.argv[3]);image=Path(sys.argv[4]);rng=random.Random(seed);root.mkdir();root.chmod(0o755);(root/'image').symlink_to(image.resolve(),target_is_directory=True)
 fields=['a','b','c','d'];configs=rng.sample(list(itertools.product(list(itertools.permutations(fields,2)),['/','-','|'],[0,1])),24);cases=[];held=[];specs=[]
 def example(pair,sep,flag):
  record={f:''.join(rng.choices('abcdefghjkmnpqrstuvwxyz',k=5)) for f in fields};record['flag']=rng.randrange(2)
  value=sep.join(record[f] for f in pair);value=value.upper() if record['flag']==flag else value.lower()
  return dict(input=record,output=value)
 for i,(pair,sep,flag) in enumerate(configs):
  name=f'Maple{i:03d}';key=f'procedure for workflow {name}';train=[example(pair,sep,flag) for _ in range(6)];dev=[example(pair,sep,flag) for _ in range(4)];test=[example(pair,sep,flag) for _ in range(20)]
  for j,e in enumerate(train):
   e['input']['flag']=j%2;value=sep.join(e['input'][f] for f in pair);e['output']=value.upper() if j%2==flag else value.lower()
  query=f'Infer the private record transformation {name} from examples: '+json.dumps(train,separators=(',',':'))+'. Return one rule in this exact grammar, replacing placeholders: Join FIELD1,FIELD2 with SEP; uppercase if flag=N, otherwise lowercase. FIELD1 and FIELD2 are input keys, SEP is the literal separator and N is 0 or 1. Return the rule only.'
  cases.append(dict(id='learn-'+name,workflow=name,key=key,domain='record-transform',source='training',query=query,examples=train,validation_examples=dev,expected='not task-scored',scorer='text'))
  for j,e in enumerate(test):held.append(dict(id=f'{name}-{j}',workflow=name,key=key,domain='record-transform',source='sealed',input=e['input'],query=f'Execute my private workflow {name} on record '+json.dumps(e['input'],separators=(',',':'))+'. Return only the transformed string. If the procedure is unknown, return unknown.',expected=e['output'],scorer='exact'))
  specs.append(dict(workflow=name,fields=pair,separator=sep,uppercase_flag=flag))
 rng.shuffle(held);save(root/'cases.json',cases);save(root/'heldout.json',held);save(root/'specification.json',specs)
 save(root/'plan.json',dict(seed=seed,workflows=24,training_examples=6,validation_examples=4,sealed_examples=20,score='exact case-sensitive full output',evaluation_feedback_to_learning=False))
elif mode=='structured-select':
 gpath,qpath,out=map(Path,sys.argv[3:6]);arm=sys.argv[6];out.mkdir();g=rows(gpath/'results.jsonl');q={r['case_spec']['key']:r for r in rows(qpath/'results.jsonl')};decisions=[];selected=[]
 pattern=re.compile(r'Join ([abcd]),([abcd]) with ([/|\-]); uppercase if flag=([01]), otherwise lowercase\.?',re.I)
 def checks(rule,c):
  m=pattern.fullmatch(rule.strip())
  if not m:return False
  for e in c['examples']+c['validation_examples']:
   value=m[3].join(e['input'][f.lower()] for f in [m[1],m[2]])
   value=value.upper() if e['input']['flag']==int(m[4]) else value.lower()
   if value!=e['output']:return False
  return True
 for r in g:
  c=r['case_spec'];other=q[c['key']];gv=checks(r['answer'],c);qv=checks(other['answer'],c)
  producer='gemma' if gv else 'qwen' if arm=='shared' and qv else 'unresolved';answer=r['answer'] if gv else other['answer'] if producer=='qwen' else 'unknown'
  decisions.append(dict(workflow=c['workflow'],gemma_valid=gv,qwen_valid=qv,producer=producer));selected.append(dict(case_spec=c,answer=answer,enabled=False,selection_provenance=producer))
 save(out/'decisions.json',decisions);(out/'results.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in selected));(out/'DONE').write_text('derived selection')
elif mode=='ablation':
 old=Path(sys.argv[3]);arm=sys.argv[4];root.mkdir();root.chmod(0o755);(root/'image').symlink_to((old/'image').resolve(),target_is_directory=True)
 work=json.loads((old/'workflows.json').read_text());prior=rows(old/'r2-selected/results.jsonl');by={x['case_spec']['key']:x['answer'] for x in prior};history=[]
 for n in [1,2]:history+=json.loads((old/f'r{n}-decisions.json').read_text())
 examples=lambda w,inputs:[dict(input=x,output=w['multiplier']*x+w['offset']) for x in inputs]
 successes=[dict(examples=examples(w,[1,4,9]),rule=by[w['key']],workflow=w['name']) for w in work if validate(by[w['key']],examples(w,[1,4,9]))['accepted']]
 cases=[]
 for w in work:
  inputs=[1,4,9]
  if arm in ('observations','combined') and not validate(by[w['key']],examples(w,inputs))['accepted']:inputs+=[2,3]
  ex=examples(w,inputs);query='Infer the private integer transformation '+w['name']+'. Training examples: '+json.dumps(ex)+'. Retained rule: '+by[w['key']]+'.'
  if arm in ('history','combined'):query+=' Prior attempts and their training checks: '+json.dumps([e for e in history if e['workflow']==w['name']])+'.'
  if arm in ('transfer','combined'):query+=' Successful example from a different workflow: '+json.dumps(next((x for x in successes if x['workflow']!=w['name']),None))+'.'
  query+=' Return only one sentence under 100 characters: Multiply the input by A and add B (or subtract B).'
  cases.append(dict(id='learn-'+w['name'],workflow=w['name'],key=w['key'],domain='affine-procedure',source='ablation',query=query,examples=ex,expected='not task-scored',scorer='text'))
 save(root/'cases.json',cases);(root/'heldout.json').write_bytes((old/'evaluation.json').read_bytes());save(root/'plan.json',dict(arm=arm,parent='experience round 2',evaluation_feedback=False))
elif mode=='ablation-select':
 old,gpath,out=map(Path,sys.argv[3:6]);qpath=Path(sys.argv[6]) if len(sys.argv)>6 else None;out.mkdir();g=rows(gpath/'results.jsonl');q={r['case_spec']['key']:r for r in rows(qpath/'results.jsonl')} if qpath else {};prior=json.loads((old/'r2-source/selected-procedures.json').read_text());selected=[]
 for r in g:
  c=r['case_spec'];gv=validate(r['answer'],c['examples'])['accepted'];donor=q.get(c['key']);qv=bool(donor and validate(donor['answer'],c['examples'])['accepted']);answer=r['answer'] if gv else donor['answer'] if qv else prior[c['key']]
  selected.append(dict(case_spec=c,enabled=False,answer=answer,selection_provenance='gemma' if gv else 'qwen' if qv else 'retained'))
 (out/'results.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in selected));(out/'DONE').write_text('derived selection')
else:raise ValueError(mode)
