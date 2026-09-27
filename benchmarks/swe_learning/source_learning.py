"""Fixed 16-task, three-round source-backed learning campaign. Private fixture."""
import concurrent.futures,hashlib,json,os,pathlib,shlex,subprocess,time,urllib.request
import run
from resume_campaign import validate_resume
from source_experience import accept_success,failure_evidence,promote,render_success
ROOT=run.ROOT;ORIGINAL=ROOT.parent

def write(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2)+'\n')
def capture(task,row,previous,source_root=ROOT):
 source=source_root/'results'/row['arm']/task['instance_id']
 out=ROOT/('results' if source_root==ROOT else 'acquisition')/row['arm']/task['instance_id'];traj=json.loads((source/'trajectory.json').read_text())
 if row['resolved'] is None:return previous
 if previous is not None and previous['kind']=='accepted_success':
  write(out/'experience-decision.json',{'decision':'retain_accepted_success','new_outcome':row['resolved'],'parent':previous['source_arm']});return previous
 if row['resolved']:
  env=run.DockerEnvironment(image=run.image(task),cwd='/testbed',timeout=45,pull_timeout=600,run_args=['--rm','--network','none','--memory','3g','--cpus','2'],interpreter=['bash','-c'],env={'BASH_ENV':'/root/.bashrc','PAGER':'cat'})
  try:
   def replay(command):
    reset=env.execute({'command':'git reset --hard '+shlex.quote(task['base_commit'])+' && git clean -fd'})
    if reset['returncode']!=0:raise RuntimeError('replay checkout failed')
    result=env.execute({'command':command})
    diff=env.execute({'command':'git diff --no-ext-diff --binary HEAD'})
    return {'returncode':result['returncode'],'output':result['output'],'patch':diff['output']}
   candidate=accept_success(task,row,traj,replay)
  finally:env.cleanup()
 else:
  candidate=failure_evidence(task,row,traj)
  # Failure memories contain observations, never a generated explanation or fix.
  facts=[]
  for observation in reversed(candidate['observations']):
   text=('An executed command failed on the previous attempt. This is a failure to avoid, not a successful procedure.\n'
         'Command:\n'+observation['command']+'\nObserved tool result:\n'+observation['observation'])
   if len(text)<=3000:
    facts=[text];break
  candidate['lesson']=('The previous attempt at this exact issue did not pass the official overall evaluation. '
                       'Inspect the current source and verify a revised approach; do not assume the prior patch was correct.'
                       +('\n'+facts[0] if facts else ''))

 candidate=promote(previous,candidate);write(out/'source-experience.json',candidate);return candidate

def prepare(task,experience,retain):
 fact=render_success(experience) if experience['kind']=='accepted_success' else experience['lesson']
 count=run.api('/tokenize',{'model':run.MODEL,'messages':[{'role':'user','content':fact}],'chat_template_kwargs':{'enable_thinking':False}})['count']
 # Never silently shorten or drop parts of a successful procedure to fit memory.
 if len(fact)>5000 or count>900:raise ValueError('complete experience exceeds this runtime preparation budget')
 for retry in range(3):
  try:
   pub=run.bridge({'op':'publish','facts':[fact],'retain':retain});assert pub['records']==1
   return pub,fact
  except (subprocess.CalledProcessError,subprocess.TimeoutExpired):
   if retry==2:raise
   time.sleep(10)

state={}
def save():
 rows=[json.loads(p.read_text()) for p in (ROOT/'results').glob('*/*/result.json')]
 state['completed']=len(rows);state['arms']={}
 baseline={r['instance_id']:r for r in rows if r['arm']=='source-control'}
 for arm in ['source-control','source-learn-1','source-learn-2','source-learn-3']:
  rs=[r for r in rows if r['arm']==arm]
  state['arms'][arm]={'completed':len(rs),'resolved':sum(r.get('resolved') is True for r in rs),'infrastructure':sum(r.get('resolved') is None for r in rs),'gained_vs_control':[r['instance_id'] for r in rs if r.get('resolved') is True and baseline.get(r['instance_id'],{}).get('resolved') is False],'lost_vs_control':[r['instance_id'] for r in rs if r.get('resolved') is False and baseline.get(r['instance_id'],{}).get('resolved') is True]}
 state['updated']=time.time();write(ROOT/'status.json',state)

if __name__=='__main__':
 os.chdir(ROOT);tasks=json.loads((ROOT/'tasks.json').read_text());run.GRADER={t['instance_id']:t for t in json.loads((ORIGINAL/'selected-grader-only.json').read_text())}
 resume_start=validate_resume(ROOT,tasks,int(os.environ.get('SWE_RESUME_GROUP','0')))
 prior_state=json.loads((ROOT/'status.json').read_text()) if resume_start and (ROOT/'status.json').exists() else {}
 state={'status':'waiting_for_fidelity','started':prior_state.get('started',time.time()),'resume_group':resume_start,'resumed_at':time.time() if resume_start else None,'scheduled_attempts':len(tasks)*4,'budget':{'seconds':run.SECONDS,'steps':run.STEPS,'output_tokens':run.OUTPUT_TOKENS,'input_tokens':run.INPUT_TOKENS,'grader_seconds':run.GRADE_TIMEOUT,'context_tokens':8192,'concurrency':2},'scope':'Same-task experience reuse with three native rounds. Eight previously calibrated tasks plus eight additional frozen-list tasks. Prior calibration learn-1 successes are automatically replay-validated and retained before this campaign; no hidden solutions. No held-out-task generalization claim.'};save()
 try:
  while True:
   prior=json.loads((ORIGINAL/'lesson-fidelity-20260927/status.json').read_text())
   if prior['status']=='complete':break
   if prior['status']=='failed':raise RuntimeError('predecessor failed; preserve comparison and inspect')
   time.sleep(15)
  with urllib.request.urlopen(run.BASE+'/v1/models',timeout=30) as response:run.MODEL=json.load(response)['data'][0]['id']
  for start in range(resume_start,len(tasks),2):
   group=tasks[start:start+2];experiences={};publications={};state.update(status='running',group_start=start);save()
   for task in group:
    if subprocess.run(['docker','image','inspect',run.image(task)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
     subprocess.run(['docker','pull',run.image(task)],check=True,timeout=600)
   for task in group:
    prior_root=ORIGINAL/'calibration-20260927'
    prior_path=prior_root/'results/learn-1'/task['instance_id']/'result.json'
    if prior_path.exists():
     prior_row=json.loads(prior_path.read_text())
     if prior_row.get('resolved') is True:experiences[task['instance_id']]=capture(task,prior_row,None,prior_root)
   for arm in ['source-control','source-learn-1','source-learn-2','source-learn-3']:
    state['current_arm']=arm;save()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
     results=list(pool.map(lambda t:run.attempt(t,arm,publications.get(t['instance_id']) if arm!='source-control' else None),group))
    save()
    if arm=='source-learn-3':continue
    for task,row in zip(group,results):
     iid=task['instance_id']
     if row['resolved'] is None:raise RuntimeError('infrastructure error, not a learning outcome: '+iid)
     experiences[iid]=capture(task,row,experiences.get(iid))
    publications={}
    for task in group:
     iid=task['instance_id'];pub,fact=prepare(task,experiences[iid],list(publications.values()));publications[iid]=pub['publication']
     write(ROOT/'results'/arm/iid/'next-publication.json',dict(pub,complete_fact=fact,fact_sha256=hashlib.sha256(fact.encode()).hexdigest()))
   # Keep images for replay and inspection; do not delete other users' shared data.
  state['status']='complete'
 except BaseException as error:state.update(status='failed',error=repr(error));raise
 finally:save()
