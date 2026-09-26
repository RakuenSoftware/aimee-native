"""Fixed-task, fixed-budget repeated learning; official grading stays outside agent containers."""
import concurrent.futures,hashlib,json,os,pathlib,re,statistics,subprocess,time,urllib.request,urllib.error
import docker
from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.docker import DockerEnvironment
from minisweagent.models.utils.actions_text import parse_regex_actions,format_observation_messages
from swebench.harness.run_evaluation import make_test_spec,run_instance
ROOT=pathlib.Path('/opt/swe-native');BASE='http://127.0.0.1:8170';SSH=['ssh','-F',str(ROOT/'ssh.conf'),'native-gpu']
STEPS=40;SECONDS=240;ROUNDS=5
SYSTEM='''You are a software engineer fixing a repository issue in /testbed. Use exactly one fenced bash command per response, with at most two brief sentences before it. Read relevant code, implement the fix, and run relevant existing tests or your own reproduction. Do not modify existing tests or commit. You may have native memory from earlier attempts: use its concrete feedback, but verify against this clean checkout. To finish, run exactly: echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git diff --no-ext-diff .\nExample:\n```bash\nls\n```'''
def api(path,body):
 req=urllib.request.Request(BASE+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 for retry in range(20):
  try:
   with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)
  except urllib.error.HTTPError as e:
   if e.code not in (429,503):raise
   time.sleep(min(1+retry,5))
 raise RuntimeError('admission unavailable')
MODEL=None
class NativeModel:
 def __init__(self,publication=None):self.publication=publication;self.calls=[]
 def get_template_vars(self):return {}
 def format_message(self,**kw):return kw
 def serialize(self):return {'native_calls':self.calls,'native_publication':self.publication}
 def query(self,messages):
  ms=[{'role':m['role'],'content':m['content']} for m in messages if m['role'] in ('system','user','assistant')]
  # Same bounded-history rule for every arm; complete initial issue retained.
  while True:
   count=api('/tokenize',{'model':MODEL,'messages':ms,'chat_template_kwargs':{'enable_thinking':False}})['count']
   if count<=7400:break
   if len(ms)<=3:raise RuntimeError('initial issue exceeds fixed context budget')
   del ms[2:4]
  body={'model':MODEL,'messages':ms,'temperature':0,'seed':20260926,'max_tokens':512,'chat_template_kwargs':{'enable_thinking':False}}
  if self.publication:body['vllm_xargs']={'aimee_publication':self.publication}
  start=time.monotonic();r=api('/v1/chat/completions',body);text=r['choices'][0]['message']['content'] or ''
  self.calls.append({'seconds':time.monotonic()-start,'usage':r['usage'],'input_messages':len(ms),'publication':self.publication})
  actions=parse_regex_actions(text,action_regex=r'```(?:bash|mswea_bash_command)\s*\n(.*?)\n```',format_error_template='Return exactly one fenced bash command. {{error}}')
  return {'role':'assistant','content':text,'extra':{'actions':actions,'cost':0.0}}
 def format_observation_messages(self,message,outputs,template_vars=None):
  return format_observation_messages(outputs,observation_template='<returncode>{{output.returncode}}</returncode>\n{{output.output[:5000]}}',template_vars=template_vars)
def bridge(body):return json.loads(subprocess.check_output(SSH,input=json.dumps(body).encode(),timeout=660))
def image(task):return 'docker.io/swebench/sweb.eval.x86_64.'+task['instance_id'].replace('__','_1776_').lower()+':latest'
def attempt(task,arm,publication):
 iid=task['instance_id'];out=ROOT/'results'/arm/iid;out.mkdir(parents=True,exist_ok=True)
 if (out/'result.json').exists():return json.loads((out/'result.json').read_text())
 row={'instance_id':iid,'arm':arm,'publication':publication,'status':'running','started':time.time()};env=None;agent=None
 try:
  env=DockerEnvironment(image=image(task),cwd='/testbed',timeout=45,pull_timeout=600,run_args=['--rm','--network','none','--memory','3g','--cpus','2'],interpreter=['bash','-c'],env={'BASH_ENV':'/root/.bashrc','PAGER':'cat'})
  # Benchmark images may include setup commits; explicitly restore the dataset base.
  reset=env.execute({'command':'git reset --hard '+task['base_commit']})
  if reset['returncode']!=0:raise RuntimeError('dataset base checkout failed')
  check=env.execute({'command':'git rev-parse HEAD'})
  if check['output'].strip()!=task['base_commit']:raise RuntimeError('checkout mismatch')
  agent=DefaultAgent(NativeModel(publication),env,system_template=SYSTEM,instance_template='Fix this issue:\n{{task}}',step_limit=STEPS,cost_limit=0,wall_time_limit_seconds=SECONDS,max_consecutive_format_errors=5,output_path=out/'trajectory.json')
  info=agent.run(task['problem_statement']);patch=env.execute({'command':'git diff --no-ext-diff --binary HEAD'})['output']
  row.update(status='predicted',exit_status=info.get('exit_status'),steps=agent.n_calls,model_patch=patch)
 except Exception as e:row.update(status='agent_error',error=repr(e),model_patch='')
 finally:
  if env is not None:env.cleanup()
 row['agent_seconds']=time.time()-row['started']
 if row['status']=='agent_error':
  row.update(resolved=None,grade_status='infrastructure_error',finished=time.time());(out/'result.json').write_text(json.dumps(row,indent=2)+'\n');return row
 # Reference patches/test definitions are accessed only by the trusted grader here.
 if not row['model_patch'].strip():
  row.update(resolved=False,grade_status='empty_prediction',finished=time.time());(out/'result.json').write_text(json.dumps(row,indent=2)+'\n');return row
 full=GRADER[iid];pred={'instance_id':iid,'model_name_or_path':'gemma-native-'+arm,'model_patch':row['model_patch']}
 try:
  spec=make_test_spec(full,namespace='swebench');result=run_instance(spec,pred,False,False,docker.from_env(),'native-20260926-'+arm,timeout=180)
  if result is None:raise RuntimeError('grader produced no report')
  (out/'grade.json').write_text(json.dumps(result,indent=2)+'\n')
  if not result['completed']:raise RuntimeError('official grader did not complete')
  row.update(resolved=bool(result['resolved']),grade_status='graded')
 except Exception as e:row.update(resolved=None,grade_status='infrastructure_error',grade_error=repr(e))
 row['finished']=time.time();(out/'result.json').write_text(json.dumps(row,indent=2)+'\n');return row

def learn(task,row,previous):
 out=ROOT/'results'/row['arm']/task['instance_id'];target=out/'experience.json'
 if target.exists():return json.loads(target.read_text())['lesson']
 traj=json.loads((out/'trajectory.json').read_text()) if (out/'trajectory.json').exists() else {}
 observations='\n'.join(m.get('content','') for m in traj.get('messages',[])[-10:])[-6000:]
 # Only pass/fail, own generated patch and agent-visible observations cross to memory.
 payload={'model':MODEL,'messages':[{'role':'user','content':f'Write a compact actionable memory for the next clean attempt at this coding issue. Keep useful earlier lessons, preserve successful changes, and explain what to try or avoid. Use specific filenames and commands from observations. Do not invent test outcomes. At most 220 words.\nIssue: {task["problem_statement"][:3000]}\nPrevious memory: {previous}\nOfficial overall outcome: {row["resolved"]} (null means infrastructure, not failure).\nOwn patch: {row["model_patch"][:4000]}\nOwn observations: {observations}'}],'temperature':0,'max_tokens':320,'chat_template_kwargs':{'enable_thinking':False}}
 r=api('/v1/chat/completions',payload);lesson=r['choices'][0]['message']['content']
 if not lesson:raise RuntimeError('empty learned memory')
 lesson=f'Coding experience for {task["instance_id"]}, {row["arm"]}; overall resolved={row["resolved"]}. '+lesson
 target.write_text(json.dumps({'lesson':lesson,'sources':['own trajectory','own patch','overall grader boolean'],'usage':r['usage'],'sha256':hashlib.sha256(lesson.encode()).hexdigest()},indent=2)+'\n');return lesson

def save_status(state):
 rows=[]
 for p in (ROOT/'results').glob('*/*/result.json'):rows.append(json.loads(p.read_text()))
 state['arms']={arm:{'completed':len(rs:=[r for r in rows if r['arm']==arm]),'graded':sum(r['resolved'] is not None for r in rs),'resolved':sum(r['resolved'] is True for r in rs),'infrastructure_errors':sum(r['resolved'] is None for r in rs)} for arm in ['control']+[f'learn-{i}' for i in range(1,ROUNDS+1)]}
 (ROOT/'status.json').write_text(json.dumps(state,indent=2)+'\n')
if __name__=='__main__':
 os.chdir(ROOT);(ROOT/'results').mkdir(exist_ok=True)
 tasks=json.loads((ROOT/'tasks.json').read_text());GRADER={r['instance_id']:r for r in json.loads((ROOT/'selected-grader-only.json').read_text())}
 with urllib.request.urlopen(BASE+'/v1/models') as r:MODEL=json.load(r)['data'][0]['id']
 state={'status':'running','target_tasks':len(tasks),'learning_rounds':ROUNDS,'started':time.time(),'budget':{'steps':STEPS,'wall_seconds':SECONDS,'max_output_tokens':512,'context_tokens':8192,'concurrency':4}};save_status(state)
 try:
  for start in range(0,len(tasks),4):
   group=tasks[start:start+4];lessons={};publications={}
   available=[]
   for task in group:
    pulled=False
    for retry in range(3):
     try:
      subprocess.run(['docker','pull',image(task)],check=True,timeout=600);pulled=True;break
     except (subprocess.CalledProcessError,subprocess.TimeoutExpired):time.sleep(5)
    if pulled:available.append(task);continue
    for skipped_arm in ['control']+[f'learn-{i}' for i in range(1,ROUNDS+1)]:
     out=ROOT/'results'/skipped_arm/task['instance_id'];out.mkdir(parents=True,exist_ok=True)
     (out/'result.json').write_text(json.dumps({'instance_id':task['instance_id'],'arm':skipped_arm,'status':'image_unavailable','resolved':None,'grade_status':'infrastructure_error','finished':time.time()},indent=2)+'\n')
   group=available
   if not group:save_status(state);continue
   for arm in ['control']+[f'learn-{i}' for i in range(1,ROUNDS+1)]:
    state.update(group_start=start,current_arm=arm);save_status(state)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
     results=list(pool.map(lambda t:attempt(t,arm,publications.get(t['instance_id']) if arm not in ('control','learn-1') else None),group))
    save_status(state)
    metrics=bridge({'op':'metrics'})
    (ROOT/f'metrics-group-{start}-{arm}.json').write_text(json.dumps(metrics,indent=2)+'\n')
    if arm!='control':
     for task,row in zip(group,results):
      if row['resolved'] is None:continue
      iid=task['instance_id'];lessons[iid]=learn(task,row,lessons.get(iid,''))
     if arm!=f'learn-{ROUNDS}':
      publications={}
      for task in group:
       iid=task['instance_id']
       if iid not in lessons:continue
       result=bridge({'op':'publish','facts':[lessons[iid]],'retain':list(publications.values())});publications[iid]=result['publication']
       (ROOT/'results'/arm/iid/'native-publication.json').write_text(json.dumps(result,indent=2)+'\n')
   for task in group:subprocess.run(['docker','image','rm',image(task)],check=False)
  state['status']='complete'
 except BaseException as e:state.update(status='failed',error=repr(e));raise
 finally:state['updated']=time.time();save_status(state)
