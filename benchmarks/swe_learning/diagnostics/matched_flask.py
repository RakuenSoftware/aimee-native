"""Balanced, fixed-lesson delivery diagnostic. No learning or feedback between trials."""
import hashlib,importlib.util,itertools,json,os,pathlib,subprocess,time,urllib.request
ROOT=pathlib.Path(os.environ['SWE_RUN_ROOT']);ORIGINAL=ROOT.parent
spec=importlib.util.spec_from_file_location('matched_runner',ROOT/'run.py');run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)
os.chdir(ROOT)
IID='pallets__flask-5014'
task=next(t for t in json.loads((ORIGINAL/'tasks.json').read_text()) if t['instance_id']==IID)
run.GRADER={t['instance_id']:t for t in json.loads((ORIGINAL/'selected-grader-only.json').read_text())}
source=ORIGINAL/'calibration-20260927/results/learn-1'/IID
assert json.loads((source/'result.json').read_text())['resolved'] is True
lesson=json.loads((source/'experience.json').read_text())['lesson']
(ROOT/'frozen-lesson.json').write_text(json.dumps({'source':str(source),'sha256':hashlib.sha256(lesson.encode()).hexdigest(),'lesson':lesson},indent=2)+'\n')
orders=list(itertools.permutations(('none','text','native')))
state={'status':'preparing','task':IID,'scheduled_attempts':18,'completed':0,'orders':orders,'budget':{'steps':run.STEPS,'seconds':run.SECONDS,'max_output_tokens':512,'context_tokens':8192,'temperature':0,'seed':20260926,'concurrency':1},'started':time.time(),'interpretation':'One previously inspected task; six repeatability trials per condition, not six independent tasks. Fixed successful lesson, no updates or outcome-based stopping.'}
def save():
 rows=[json.loads(p.read_text()) for p in (ROOT/'results').glob('*/*/result.json')]
 state['completed']=len(rows);state['arms']={mode:{'completed':len(rs:=[r for r in rows if r['arm'].endswith('-'+mode)]),'resolved':sum(r.get('resolved') is True for r in rs),'infrastructure':sum(r.get('resolved') is None for r in rs)} for mode in ('none','text','native')}
 (ROOT/'status.json').write_text(json.dumps(state,indent=2)+'\n')
save()
try:
 with urllib.request.urlopen(run.BASE+'/v1/models',timeout=30) as r:run.MODEL=json.load(r)['data'][0]['id']
 assert run.bridge({'op':'metrics'}).get('active_requests',0)==0,'shared engine has active requests'
 publication=run.bridge({'op':'publish','facts':[lesson],'retain':[]})
 assert publication['records']==1
 (ROOT/'native-publication.json').write_text(json.dumps(publication,indent=2)+'\n')
 if subprocess.run(['docker','image','inspect',run.image(task)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
  subprocess.run(['docker','pull',run.image(task)],check=True,timeout=600)
 state['status']='running';save()
 for repetition,order in enumerate(orders,1):
  for mode in order:
   state.update(repetition=repetition,current_mode=mode);save()
   result=run.attempt(task,f'matched-{repetition}-{mode}',publication['publication'] if mode=='native' else None,lesson if mode=='text' else None)
   save();print(json.dumps({k:result.get(k) for k in ('arm','resolved','exit_status','grade_status','agent_seconds')}),flush=True)
 state['status']='complete'
except BaseException as error:state.update(status='failed',error=repr(error));raise
finally:state['updated']=time.time();save()
