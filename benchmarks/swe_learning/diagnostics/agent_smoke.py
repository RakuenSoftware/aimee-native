"""Full clean-checkout agent replay of four diagnosed tasks, outside campaign scores."""
import concurrent.futures,importlib.util,json,os,pathlib,subprocess,urllib.request
original=pathlib.Path('/opt/swe-native');root=original/'repair-smoke-20260927';root.mkdir(exist_ok=True)
os.environ['SWE_RUN_ROOT']=str(root)
spec=importlib.util.spec_from_file_location('repair_runner',root/'run.py');run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)
run.GRADER={r['instance_id']:r for r in json.loads((original/'selected-grader-only.json').read_text())}
with urllib.request.urlopen(run.BASE+'/v1/models') as r:run.MODEL=json.load(r)['data'][0]['id']
tasks=json.loads((original/'tasks.json').read_text())[:4]
pubs={r['task']:r['key'] for r in json.loads((original/'fp32-lessons.json').read_text())}
def execute(task):
    subprocess.run(['docker','pull',run.image(task)],check=True,timeout=600,stdout=subprocess.DEVNULL)
    result=run.attempt(task,'repair-native-replay',pubs[task['instance_id']])
    print(json.dumps({k:result.get(k) for k in ('instance_id','exit_status','resolved','grade_status','agent_seconds')}),flush=True)
    return result
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(execute,tasks))
(root/'summary.json').write_text(json.dumps({'scope':'Post-hoc four-task repair replay, not an independent learning effect estimate','results':results},indent=2)+'\n')
