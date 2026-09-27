"""Post-matched, fixed source-evidence ablation. Never alters the matched run."""
import hashlib,importlib.util,json,os,pathlib,subprocess,time,urllib.request
ROOT=pathlib.Path(os.environ['SWE_RUN_ROOT']);ORIGINAL=ROOT.parent
spec=importlib.util.spec_from_file_location('fidelity_runner',ROOT/'run.py');run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)
os.chdir(ROOT)
IID='pallets__flask-5014'
task=next(t for t in json.loads((ORIGINAL/'tasks.json').read_text()) if t['instance_id']==IID)
run.GRADER={t['instance_id']:t for t in json.loads((ORIGINAL/'selected-grader-only.json').read_text())}
source=ORIGINAL/'calibration-20260927/results/learn-1'/IID
assert json.loads((source/'result.json').read_text())['resolved'] is True
lesson=json.loads((source/'experience.json').read_text())['lesson']
trajectory=json.loads((source/'trajectory.json').read_text())
commands=[a['command'] for m in trajectory['messages'] for a in m.get('extra',{}).get('actions',[])]
command=next(c for c in commands if c.startswith("sed -i '/self.name = name/i"))
# Preserve actual successful agent evidence; never read a gold patch.
action='Observed successful edit for this exact issue on a clean checkout, in /testbed:\n```bash\n'+command+'\n```\nThe source attempt passed pytest tests/test_blueprints.py and the official overall grader. Inspect the checkout before applying; do not repeat an already-applied edit.'
variants={'summary_plus_action':lesson+'\n\n'+action,'action_only':action,'invariant_only':'In src/flask/blueprints.py, Blueprint.__init__ must raise ValueError when name is empty. Preserve the existing rejection of names containing a dot and all constructor assignments. Validate with pytest tests/test_blueprints.py.'}
orders=[('control_before','none',None),('summary_plus_action','text',variants['summary_plus_action']),('action_only','native',variants['action_only']),('invariant_only','text',variants['invariant_only']),('summary_plus_action','native',variants['summary_plus_action']),('action_only','text',variants['action_only']),('invariant_only','native',variants['invariant_only']),('control_after','none',None)]
(ROOT/'frozen-variants.json').write_text(json.dumps({k:{'lesson':v,'sha256':hashlib.sha256(v.encode()).hexdigest()} for k,v in variants.items()},indent=2)+'\n')
state={'status':'waiting_for_matched','started':time.time(),'scheduled_attempts':len(orders),'completed':0,'orders':[[v,m] for v,m,_ in orders],'interpretation':'Exploratory single-task lesson-representation ablation, one trial per cell, unchanged editing tools and budgets. Not a learning-effect estimate.'}
def save():
 rows=[json.loads(p.read_text()) for p in (ROOT/'results').glob('*/*/result.json')]
 state['completed']=len(rows);state['results']=[{k:r.get(k) for k in ('arm','resolved','exit_status','grade_status','agent_seconds')} for r in rows];state['updated']=time.time()
 (ROOT/'status.json').write_text(json.dumps(state,indent=2)+'\n')
save()
try:
 while True:
  preceding=json.loads((ORIGINAL/'matched-flask-20260927/status.json').read_text())
  if preceding['status']=='complete':break
  if preceding['status']=='failed':raise RuntimeError('matched driver failed; investigate before proceeding')
  time.sleep(15)
 with urllib.request.urlopen(run.BASE+'/v1/models',timeout=30) as r:run.MODEL=json.load(r)['data'][0]['id']
 assert run.bridge({'op':'metrics'}).get('active_requests',0)==0
 publications={};state['status']='preparing';save()
 for variant,fact in variants.items():
  pub=run.bridge({'op':'publish','facts':[fact],'retain':list(publications.values())})
  assert pub['records']==1
  publications[variant]=pub['publication']
  (ROOT/(variant+'-publication.json')).write_text(json.dumps(pub,indent=2)+'\n')
 if subprocess.run(['docker','image','inspect',run.image(task)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
  subprocess.run(['docker','pull',run.image(task)],check=True,timeout=600)
 state['status']='running';save()
 for variant,mode,fact in orders:
  state.update(current_variant=variant,current_mode=mode);save()
  run.attempt(task,'fidelity-'+variant+'-'+mode,publications[variant] if mode=='native' else None,fact if mode=='text' else None)
  save()
 state['status']='complete'
except BaseException as error:state.update(status='failed',error=repr(error));raise
finally:save()
