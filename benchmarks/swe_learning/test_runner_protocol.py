"""Runner recovery must retain rejected output and never execute ambiguous actions."""
import importlib.util,pathlib,unittest
from unittest.mock import patch
from minisweagent.exceptions import FormatError
spec=importlib.util.spec_from_file_location('runner_under_test',pathlib.Path(__file__).with_name('run.py'))
run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)

class Recovery(unittest.TestCase):
 def query(self,text,reason='stop'):
  responses=[{'count':20},{'choices':[{'message':{'content':text},'finish_reason':reason}],'usage':{'prompt_tokens':20,'completion_tokens':5}}]
  with patch.object(run,'api',side_effect=responses):return run.NativeModel().query([{'role':'user','content':'Fix the issue'}])
 def test_multiple_actions_are_preserved_for_recovery_not_executed(self):
  text='```bash\nls\n```\nActually:\n```bash\npwd\n```'
  with self.assertRaises(FormatError) as caught:self.query(text)
  messages=caught.exception.messages
  self.assertEqual([m['role'] for m in messages],['assistant','user'])
  self.assertEqual(messages[0]['content'],text)
  self.assertIn('found 2',messages[1]['content'])
  self.assertNotIn('actions',messages[0]['extra'])
 def test_truncation_retains_response_and_explains_recovery(self):
  with self.assertRaises(FormatError) as caught:self.query('```bash\nunfinished','length')
  self.assertEqual(caught.exception.messages[0]['content'],'```bash\nunfinished')
  self.assertIn('exceeded the output limit',caught.exception.messages[1]['content'])
 def test_valid_single_action_is_unchanged(self):
  self.assertEqual(self.query('```bash\npwd\n```')['extra']['actions'],[{'command':'pwd'}])

class Delivery(unittest.TestCase):
 def test_delivery_is_exclusive_and_does_not_mutate_history(self):
  original=[{'role':'system','content':'Common instructions'},{'role':'user','content':'Issue'}]
  for mode in ('none','text','native'):
   model=run.NativeModel(publication='fixture' if mode=='native' else None,text_memory='Complete lesson' if mode=='text' else None)
   responses=[{'count':20},{'choices':[{'message':{'content':'```bash\npwd\n```'},'finish_reason':'stop'}],'usage':{}}]
   with patch.object(run,'api',side_effect=responses) as api:model.query(original)
   request=api.call_args.args[1]
   self.assertEqual(original[0]['content'],'Common instructions')
   self.assertEqual(request['messages'][0]['content'],'Common instructions'+('\n\nAuthoritative memory:\nComplete lesson' if mode=='text' else ''))
   self.assertEqual('vllm_xargs' in request,mode=='native')
 def test_mixed_delivery_is_rejected(self):
  with self.assertRaises(ValueError):run.NativeModel('fixture','lesson')

if __name__=='__main__':unittest.main()
