"""Retry trusted grading of an unchanged saved prediction, retaining prior evidence."""
import argparse,hashlib,json,os,pathlib,time

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--instance',required=True);p.add_argument('--arm',default='source-control',choices=['source-control','source-learn-1']);p.add_argument('--timeout',type=int,required=True);args=p.parse_args()
 import docker
 from swebench.harness.run_evaluation import make_test_spec,run_instance
 root=args.root;os.chdir(root);out=root/'results'/args.arm/args.instance;path=out/'result.json';row=json.loads(path.read_text())
 assert row['instance_id']==args.instance and row['arm']==args.arm and row.get('resolved') is None and row['model_patch'].strip()
 stamp=str(int(time.time()));archive=out/('grading-retry-'+stamp);archive.mkdir();(archive/'original-result.json').write_bytes(path.read_bytes())
 report={'status':'running','started':time.time(),'timeout_seconds':args.timeout,'patch_sha256':hashlib.sha256(row['model_patch'].encode()).hexdigest(),'scope':'Identical generated patch and official tests; extended grading deadline only. No model rerun.'}
 report_path=archive/'retry.json';report_path.write_text(json.dumps(report,indent=2)+'\n')
 try:
  full=next(t for t in json.loads((root.parent/'selected-grader-only.json').read_text()) if t['instance_id']==args.instance)
  pred={'instance_id':args.instance,'model_name_or_path':'gemma-native-'+args.arm,'model_patch':row['model_patch']}
  result=run_instance(make_test_spec(full,namespace='swebench'),pred,False,False,docker.from_env(),'native-regrade-'+stamp,timeout=args.timeout)
  (archive/'grade.json').write_text(json.dumps(result,indent=2)+'\n')
  if not result or not result['completed']:raise RuntimeError('official grader did not complete')
  row.update(resolved=bool(result['resolved']),grade_status='graded',grade_timeout_seconds=args.timeout,regraded_at=time.time(),regrade_evidence=str(archive.relative_to(root)))
  row.pop('grade_error',None);tmp=path.with_suffix('.next');tmp.write_text(json.dumps(row,indent=2)+'\n');tmp.replace(path)
  report.update(status='complete',resolved=row['resolved'])
 except BaseException as error:
  report.update(status='failed',error=repr(error));(root/'deferred-grading-failed.json').write_text(json.dumps(report,indent=2)+'\n');raise
 finally:
  report['finished']=time.time();report_path.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
