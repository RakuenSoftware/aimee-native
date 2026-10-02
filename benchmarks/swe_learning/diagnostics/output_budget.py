"""Exploratory matched output-budget diagnostic; not part of the fixed campaign.
Deploy beside its version of run.py. No memory learning or publication mutation.
"""
import concurrent.futures,json,os,pathlib,time,urllib.request
import run
ROOT=run.ROOT;SOURCE=ROOT.parent/'source-learning-20260927'
if __name__=='__main__':
 if run.OUTPUT_TOKENS!=1536:raise ValueError('this diagnostic requires 1536 output tokens')
 ROOT.mkdir(exist_ok=True);os.chdir(ROOT);task=next(t for t in json.loads((SOURCE/'tasks.json').read_text()) if t['instance_id']=='matplotlib__matplotlib-25340')
 publication=json.loads((SOURCE/'results/source-control'/task['instance_id']/'next-publication.json').read_text())
 run.GRADER={t['instance_id']:t for t in json.loads((ROOT.parent/'selected-grader-only.json').read_text())}
 with urllib.request.urlopen(run.BASE+'/v1/models',timeout=20) as response:run.MODEL=json.load(response)['data'][0]['id']
 state={'status':'running','started':time.time(),'scope':'Post-hoc output/context-budget diagnostic on the task with observed command truncations. Uses the same retained prior procedure; no new learning and no change to the fixed campaign.','budget':{'output_tokens':run.OUTPUT_TOKENS,'input_tokens':run.INPUT_TOKENS,'seconds':run.SECONDS,'steps':run.STEPS,'grader_seconds':run.GRADE_TIMEOUT,'concurrency':2},'publication':publication['publication'],'fact_sha256':publication['fact_sha256']}
 def save():(ROOT/'status.json').write_text(json.dumps(state,indent=2)+'\n')
 save()
 try:
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
   results=list(pool.map(lambda arm:run.attempt(task,arm,publication['publication'] if arm.endswith('-native') else None),['budget1536-control','budget1536-native']))
  state['results']=[{k:r.get(k) for k in ['arm','resolved','grade_status','exit_status','steps','agent_seconds']} for r in results]
  state['status']='complete' if all(r.get('resolved') is not None for r in results) else 'failed'
 except BaseException as error:state.update(status='failed',error=repr(error));raise
 finally:state['finished']=time.time();save()
