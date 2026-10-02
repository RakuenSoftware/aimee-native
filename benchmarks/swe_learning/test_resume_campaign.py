import json,pathlib,tempfile,unittest
from resume_campaign import validate_resume

class Resume(unittest.TestCase):
 def test_missing_or_ungraded_prefix_is_rejected(self):
  with tempfile.TemporaryDirectory() as temp:
   root=pathlib.Path(temp);tasks=[{'instance_id':x} for x in ('a','b','c','d')]
   self.assertEqual(validate_resume(root,tasks,0),0)
   for start in (-2,1,6):
    with self.assertRaises(ValueError):validate_resume(root,tasks,start)
   with self.assertRaises(ValueError):validate_resume(root,tasks,2)
   for task in tasks[:2]:
    for arm in ('source-control','source-learn-1','source-learn-2','source-learn-3'):
     p=root/'results'/arm/task['instance_id']/'result.json';p.parent.mkdir(parents=True);p.write_text(json.dumps({'instance_id':task['instance_id'],'arm':arm,'resolved':False}))
   self.assertEqual(validate_resume(root,tasks,2),2)
   row=json.loads(p.read_text());row['resolved']=None;p.write_text(json.dumps(row))
   with self.assertRaises(ValueError):validate_resume(root,tasks,2)

if __name__=='__main__':unittest.main()
