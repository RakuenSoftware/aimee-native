"""Exercise concurrent publication retention without model calls or Docker."""
import concurrent.futures,importlib.util,json,pathlib,tempfile,threading,types,unittest
from unittest.mock import patch

class BroaderPipelines(unittest.TestCase):
 def test_concurrent_native_requests_keep_each_others_publications(self):
  with tempfile.TemporaryDirectory() as temp:
   root=pathlib.Path(temp);barrier=threading.Barrier(4);lock=threading.Lock();inside=set();catalog=set();retained=[]
   def write(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))
   def attempt(task,arm,publication):
    if publication:
     with lock:
      self.assertIn(publication,catalog);inside.add(publication)
     barrier.wait(timeout=10)
     with lock:
      self.assertTrue(inside<=catalog);inside.remove(publication)
    row={'instance_id':task['instance_id'],'arm':arm,'resolved':True}
    write(root/'results'/arm/task['instance_id']/'result.json',row);return row
   def prepare(task,experience,retain):
    pub='publication-'+task['instance_id']
    with lock:
     self.assertTrue(inside<=set(retain));catalog.clear();catalog.update(retain+[pub]);retained.append(retain)
    return {'publication':pub,'records':1},'complete procedure '+task['instance_id']
   run=types.ModuleType('run');run.ROOT=root;run.attempt=attempt
   source=types.ModuleType('source_learning');source.capture=lambda *a: {'kind':'accepted_success'};source.prepare=prepare;source.write=write
   spec=importlib.util.spec_from_file_location('broader_test',pathlib.Path(__file__).with_name('broader_source_learning.py'));module=importlib.util.module_from_spec(spec)
   with patch.dict('sys.modules',{'run':run,'source_learning':source}):spec.loader.exec_module(module)
   # A partially written unrelated result must not derail other pipelines.
   write(root/'results/other/task/result.json',{});(root/'results/other/task/result.json').write_text('{')
   with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(module.task_pipeline,[{'instance_id':str(i)} for i in range(4)]))
   self.assertEqual(len(rows),4);self.assertEqual(sorted(map(len,retained)),[0,1,2,3]);self.assertEqual(module.active_publications,{})
   status=json.loads((root/'status.json').read_text());self.assertEqual(status['graded_attempts'],8)

 def test_completed_pair_is_not_replayed_or_republished_on_resume(self):
  with tempfile.TemporaryDirectory() as temp:
   root=pathlib.Path(temp);run=types.ModuleType('run');run.ROOT=root
   def forbidden(*args):raise AssertionError('completed pair must stay untouched')
   run.attempt=forbidden;source=types.ModuleType('source_learning');source.capture=forbidden;source.prepare=forbidden
   for arm in ['source-control','source-learn-1']:
    p=root/'results'/arm/'task'/'result.json';p.parent.mkdir(parents=True);p.write_text(json.dumps({'instance_id':'task','arm':arm,'resolved':True}))
   spec=importlib.util.spec_from_file_location('broader_resume_test',pathlib.Path(__file__).with_name('broader_source_learning.py'));module=importlib.util.module_from_spec(spec)
   with patch.dict('sys.modules',{'run':run,'source_learning':source}):spec.loader.exec_module(module)
   self.assertEqual(module.task_pipeline({'instance_id':'task'}),{'instance_id':'task','control':True,'native':True})
   module.STOP.set()
   with self.assertRaises(concurrent.futures.CancelledError):module.task_pipeline({'instance_id':'new'})

 def test_ungraded_result_requires_archiving_before_resume(self):
  with tempfile.TemporaryDirectory() as temp:
   root=pathlib.Path(temp);run=types.ModuleType('run');run.ROOT=root;source=types.ModuleType('source_learning')
   p=root/'results/source-control/task/result.json';p.parent.mkdir(parents=True);p.write_text(json.dumps({'instance_id':'task','arm':'source-control','resolved':None}))
   spec=importlib.util.spec_from_file_location('broader_invalid_test',pathlib.Path(__file__).with_name('broader_source_learning.py'));module=importlib.util.module_from_spec(spec)
   with patch.dict('sys.modules',{'run':run,'source_learning':source}):spec.loader.exec_module(module)
   with self.assertRaisesRegex(ValueError,'archive ungraded'):module.task_pipeline({'instance_id':'task'})

if __name__=='__main__':unittest.main()
