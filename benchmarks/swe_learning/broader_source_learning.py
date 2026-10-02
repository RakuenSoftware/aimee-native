"""Additional frozen tasks, one source-backed native attempt after each control.
Four independent task pipelines; no barrier on unrelated CPU grading. No prior
calibration experience is supplied. Runs only after the primary campaign ends.
"""
import concurrent.futures,hashlib,json,os,pathlib,subprocess,threading,time,urllib.request
import run
import source_learning as source
from resume_campaign import validate_resume

ROOT=run.ROOT
PRIMARY=ROOT.parent/'source-learning-20260927'
PUBLICATION_LOCK=threading.Lock()
STATE_LOCK=threading.Lock()
active_publications={}
state={}
STOP=threading.Event()

def save():
 with STATE_LOCK:
  rows=[]
  for p in (ROOT/'results').glob('*/*/result.json'):
   try:rows.append(json.loads(p.read_text()))
   except json.JSONDecodeError:continue  # Another worker can be finishing a write.
  state['recorded_attempts']=len(rows)
  state['graded_attempts']=sum(type(r.get('resolved')) is bool for r in rows)
  state['updated']=time.time()
  p=ROOT/'status.next';p.write_text(json.dumps(state,indent=2)+'\n');p.replace(ROOT/'status.json')

def task_pipeline(task):
 iid=task['instance_id']
 if STOP.is_set():raise concurrent.futures.CancelledError()
 # Completed pairs remain untouched on infrastructure recovery.
 prior=[]
 for arm in ['source-control','source-learn-1']:
  p=ROOT/'results'/arm/iid/'result.json'
  if p.exists():
   row=json.loads(p.read_text())
   if row['instance_id']!=iid or row['arm']!=arm:raise ValueError('resume identity mismatch')
   if type(row.get('resolved')) is not bool:raise ValueError('archive ungraded interruption before resuming: '+str(p))
   prior.append(row)
 if len(prior)==2:return {'instance_id':iid,'control':prior[0]['resolved'],'native':prior[1]['resolved']}
 try:
  control=run.attempt(task,'source-control',None)
  if type(control.get('resolved')) is not bool:raise RuntimeError('ungraded control: '+iid)
  save()
  if STOP.is_set():raise concurrent.futures.CancelledError()
  experience=source.capture(task,control,None)
  with PUBLICATION_LOCK:
   if STOP.is_set():raise concurrent.futures.CancelledError()
   pub,fact=source.prepare(task,experience,list(active_publications.values()))
   active_publications[iid]=pub['publication']
   source.write(ROOT/'results/source-control'/iid/'next-publication.json',dict(pub,complete_fact=fact,fact_sha256=hashlib.sha256(fact.encode()).hexdigest()))
  if STOP.is_set():raise concurrent.futures.CancelledError()
  native=run.attempt(task,'source-learn-1',pub['publication'])
  if type(native.get('resolved')) is not bool:raise RuntimeError('ungraded native attempt: '+iid)
  return {'instance_id':iid,'control':control['resolved'],'native':native['resolved']}
 finally:
  # A finished attempt has no outstanding inference request. Other active banks
  # remain in every subsequent publish's retained set under the same lock.
  with PUBLICATION_LOCK:active_publications.pop(iid,None)
  save()

def main():
 os.chdir(ROOT)
 tasks=json.loads((ROOT/'tasks.json').read_text())
 if len(tasks)!=32 or len({t['instance_id'] for t in tasks})!=32:raise ValueError('expected 32 unique frozen tasks')
 STOP.clear()
 state.update(status='waiting_for_primary',started=time.time(),scheduled_attempts=64,budget={'seconds':run.SECONDS,'steps':run.STEPS,'output_tokens':run.OUTPUT_TOKENS,'input_tokens':run.INPUT_TOKENS,'grader_seconds':run.GRADE_TIMEOUT,'concurrency':4},scope='Additional frozen tasks. One control followed by one native reuse attempt per task; no prior calibration memories supplied. Not a three-round study or a held-out generalization claim.',results=[],errors=[],cancelled_tasks=[])
 save()
 try:
  while True:
   prior=json.loads((PRIMARY/'status.json').read_text())
   if prior['status']=='complete':
    primary_tasks=json.loads((PRIMARY/'tasks.json').read_text());validate_resume(PRIMARY,primary_tasks,len(primary_tasks));break
   if prior['status']=='failed':raise RuntimeError('primary experiment failed')
   pid=int((PRIMARY/'pid').read_text());cmd=(pathlib.Path('/proc')/str(pid)/'cmdline').read_bytes()
   if b'source_learning.py' not in cmd:raise RuntimeError('primary worker is not running')
   time.sleep(15)
  state['status']='waiting_for_images';save()
  while True:
   readiness=json.loads((ROOT/'image-readiness.json').read_text())
   if readiness['status']=='complete':break
   if readiness['status']=='failed':raise RuntimeError('image prefetch failed: '+readiness.get('error','unknown'))
   time.sleep(15)
  # No on-demand image pulls may bypass the operator's storage reserve checks.
  for task in tasks:subprocess.run(['docker','image','inspect',run.image(task)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  run.GRADER={t['instance_id']:t for t in json.loads((ROOT.parent/'selected-grader-only.json').read_text())}
  with urllib.request.urlopen(run.BASE+'/v1/models',timeout=30) as response:run.MODEL=json.load(response)['data'][0]['id']
  state['status']='running';state['inference_started']=time.time();save()
  deferred_file=ROOT/'deferred-grading.json'
  deferred=json.loads(deferred_file.read_text()) if deferred_file.exists() else {}
  if not set(deferred)<=set(t['instance_id'] for t in tasks):raise ValueError('unknown deferred task')
  state['deferred_grading']=deferred;save()
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
   futures={pool.submit(task_pipeline,task):task['instance_id'] for task in tasks if task['instance_id'] not in deferred}
   for future in concurrent.futures.as_completed(futures):
    try:state['results'].append(future.result())
    except concurrent.futures.CancelledError:state['cancelled_tasks'].append(futures[future])
    except Exception as error:
     state['errors'].append({'instance_id':futures[future],'error':repr(error)})
     STOP.set()
     for pending in futures:pending.cancel()
    save()
  if not state['errors']:
   for task in tasks:
    if task['instance_id'] not in deferred:continue
    state['status']='waiting_for_deferred_grading';save()
    result_path=ROOT/'results/source-control'/task['instance_id']/'result.json'
    while type(json.loads(result_path.read_text()).get('resolved')) is not bool:
     marker=ROOT/'deferred-grading-failed.json'
     if marker.exists():raise RuntimeError('deferred grader failed: '+marker.read_text())
     time.sleep(15)
    state['status']='running';save();state['results'].append(task_pipeline(task));save()
   for task in tasks:
    for arm in ['source-control','source-learn-1']:
     row=json.loads((ROOT/'results'/arm/task['instance_id']/'result.json').read_text())
     if row['instance_id']!=task['instance_id'] or row['arm']!=arm or type(row.get('resolved')) is not bool:raise ValueError('incomplete result audit')
  state['status']='failed' if state['errors'] else 'complete'
 except BaseException as error:state.update(status='failed',error=repr(error));raise
 finally:state['finished']=time.time();save()

if __name__=='__main__':main()
