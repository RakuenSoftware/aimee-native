"""Isolation gates for the queued diagnostic; no GPU or benchmark dependency."""
import importlib.util,json,os,pathlib,tempfile,types,unittest,urllib.request
from unittest.mock import patch

class FidelityQueue(unittest.TestCase):
 def execute(self,preceding):
  with tempfile.TemporaryDirectory() as tmp:
   parent=pathlib.Path(tmp);root=parent/'followup';root.mkdir()
   iid='pallets__flask-5014'
   (parent/'tasks.json').write_text(json.dumps([{'instance_id':iid}]))
   (parent/'selected-grader-only.json').write_text(json.dumps([{'instance_id':iid}]))
   source=parent/'calibration-20260927/results/learn-1'/iid;source.mkdir(parents=True)
   for name,data in {'result.json':{'resolved':True},'experience.json':{'lesson':'Frozen original lesson'},'trajectory.json':{'messages':[{'extra':{'actions':[{'command':"sed -i '/self.name = name/i example' source.py"}]}}]}}.items():(source/name).write_text(json.dumps(data))
   match=parent/'matched-flask-20260927';match.mkdir();status=match/'status.json';status.write_text(json.dumps({'status':preceding}))
   events=[];pubs={}
   def bridge(body):
    self.assertEqual(json.loads(status.read_text())['status'],'complete')
    events.append(body['op'])
    if body['op']=='metrics':return {'active_requests':0}
    key='pub-'+str(len(pubs));pubs[key]=body['facts'][0]
    self.assertEqual(set(body['retain']),set(pubs)-{key})
    return {'publication':key,'records':1}
   def attempt(task,arm,publication,text):
    self.assertFalse(publication and text)
    if arm.endswith('-native'):self.assertIn(publication,pubs);self.assertIsNone(text)
    elif arm.endswith('-text'):self.assertIn(text,pubs.values());self.assertIsNone(publication)
    else:self.assertIsNone(text);self.assertIsNone(publication)
    events.append(arm)
   fake=types.SimpleNamespace(BASE='unused',bridge=bridge,image=lambda t:'fixture',attempt=attempt)
   spec=types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=lambda m:None))
   def release(_):
    self.assertFalse(events);status.write_text('{"status":"complete"}')
   import io,subprocess,time
   before=os.getcwd()
   try:
    with patch.dict(os.environ,{'SWE_RUN_ROOT':str(root)}),patch.object(importlib.util,'spec_from_file_location',return_value=spec),patch.object(importlib.util,'module_from_spec',return_value=fake),patch.object(urllib.request,'urlopen',return_value=io.StringIO('{"data":[{"id":"fixture"}]}')),patch.object(subprocess,'run',return_value=types.SimpleNamespace(returncode=0)),patch.object(time,'sleep',side_effect=release):
     exec(compile(pathlib.Path(__file__).with_name('lesson_fidelity.py').read_text(),'lesson_fidelity.py','exec'),{})
   finally:os.chdir(before)
   self.assertEqual(sum(e.startswith('fidelity-') for e in events),8)
   self.assertEqual(json.loads((root/'status.json').read_text())['status'],'complete')
 def test_waits_before_publication_and_delivers_exclusive_full_records(self):self.execute('running')
 def test_failed_predecessor_does_not_start(self):
  with self.assertRaisesRegex(RuntimeError,'matched driver failed'):self.execute('failed')

if __name__=='__main__':unittest.main()
