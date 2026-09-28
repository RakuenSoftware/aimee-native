import json,pathlib,tempfile,unittest
from report_source_learning import audit,ARMS

class PairedAudit(unittest.TestCase):
    def test_task_gains_are_deduplicated_and_missing_is_not_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);(root/'tasks.json').write_text(json.dumps([{'instance_id':x} for x in ('a','b','c')]))
            values={'a':[False,True,True,True],'b':[True,False,True],'c':[None]}
            for iid,results in values.items():
                for arm,resolved in zip(ARMS,results):
                    path=root/'results'/arm/iid/'result.json';path.parent.mkdir(parents=True);path.write_text(json.dumps({'arm':arm,'instance_id':iid,'resolved':resolved}))
            result=audit(root)
            self.assertEqual(result['completed_attempts'],8)
            self.assertEqual(result['status'],'partial')
            self.assertEqual(result['unique_gained_tasks'],['a'])
            self.assertEqual(result['gains_retained_all_three_rounds'],['a'])
            self.assertEqual(result['unique_lost_tasks'],['b'])
            self.assertEqual(result['arms']['source-control']['infrastructure_errors'],1)
            self.assertEqual(result['arms']['source-learn-3']['failed'],0)
            path=root/'results/source-learn-3/b/result.json';path.parent.mkdir(parents=True);path.write_text('{')
            result=audit(root)
            self.assertEqual(len(result['pending_write_files']),1)
            self.assertEqual(result['completed_attempts'],8)

    def test_all_files_present_does_not_mean_grading_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);(root/'tasks.json').write_text(json.dumps([{'instance_id':'a'}]))
            for arm in ARMS:
                path=root/'results'/arm/'a'/'result.json';path.parent.mkdir(parents=True)
                path.write_text(json.dumps({'arm':arm,'instance_id':'a','resolved':None if arm==ARMS[-1] else False}))
            result=audit(root)
            self.assertEqual(result['completed_attempts'],4)
            self.assertEqual(result['graded_attempts'],3)
            self.assertEqual(result['status'],'incomplete_grading')
            row=json.loads(path.read_text());row['resolved']=False;path.write_text(json.dumps(row))
            self.assertEqual(audit(root)['status'],'complete')

if __name__=='__main__':unittest.main()
