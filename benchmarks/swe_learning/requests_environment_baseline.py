import pathlib,json,os,time
import docker
from swebench.harness.run_evaluation import make_test_spec,run_instance
root=pathlib.Path('/opt/swe-native/broader-source-learning-20260928');os.chdir(root)
out=root/'requests-environment-baseline';out.mkdir(exist_ok=False)
full=next(t for t in json.loads((root.parent/'selected-grader-only.json').read_text()) if t['instance_id']=='psf__requests-2193')
# Harness requires an applicable patch. This marker leaves all implementation and
# test files unchanged and is ignored by the explicit official test command.
patch='diff --git a/.aimee-environment-baseline b/.aimee-environment-baseline\nnew file mode 100644\n--- /dev/null\n+++ b/.aimee-environment-baseline\n@@ -0,0 +1 @@\n+Unmodified implementation; official grader environment diagnostic.\n'
report={'status':'running','started':time.time(),'scope':'Unmodified base implementation plus inert marker; official tests and 3600-second deadline; not a model attempt.'}
try:
 result=run_instance(make_test_spec(full,namespace='swebench'),{'instance_id':full['instance_id'],'model_name_or_path':'requests-environment-baseline','model_patch':patch},False,False,docker.from_env(),'native-requests-baseline-20260928',timeout=3600)
 report.update(status='complete' if result and result['completed'] else 'incomplete',result=result)
finally:
 report['finished']=time.time();(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
