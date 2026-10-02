"""Runner recovery must retain rejected output and never execute ambiguous actions."""
import importlib.util,pathlib,unittest,os
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

class OutputBudget(unittest.TestCase):
 def test_larger_output_reserves_context_and_preserves_initial_issue(self):
  original=[{'role':'system','content':'Common instructions'},{'role':'user','content':'Original issue'},{'role':'assistant','content':'Old action'},{'role':'user','content':'Old observation'},{'role':'assistant','content':'Recent action'},{'role':'user','content':'Recent observation'}]
  for mode in ('none','text','native'):
   model=run.NativeModel(publication='fixture' if mode=='native' else None,text_memory='Complete lesson' if mode=='text' else None)
   responses=[{'count':7000},{'count':6000},{'choices':[{'message':{'content':'```bash\npwd\n```'},'finish_reason':'stop'}],'usage':{}}]
   with patch.object(run,'OUTPUT_TOKENS',1536),patch.object(run,'INPUT_TOKENS',6376),patch.object(run,'api',side_effect=responses) as api:model.query(original)
   request=api.call_args.args[1]
   self.assertEqual(request['max_tokens'],1536)
   self.assertEqual(len(request['messages']),4)
   self.assertEqual(request['messages'][1]['content'],'Original issue')
   self.assertEqual(len(original),6)
   self.assertEqual(request['messages'][-1]['content'],'Recent observation')

class CandidateContext(unittest.TestCase):
 def test_candidate_context_reserves_output_and_keeps_legacy_default(self):
  for context,expected in [('4096',2280),('8192',6376)]:
   with patch.dict(os.environ,{'SWE_CONTEXT_TOKENS':context,'SWE_OUTPUT_TOKENS':'1536'}):
    candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)
   self.assertEqual(candidate.CONTEXT_TOKENS,int(context))
   self.assertEqual(candidate.INPUT_TOKENS,expected)
 def test_complete_initial_issue_is_never_cut_to_fit(self):
  for mode in ('none','text','native'):
   original=[{'role':'system','content':'Common instructions'},{'role':'user','content':'Complete issue'}]
   model=run.NativeModel(publication='fixture' if mode=='native' else None,text_memory='Complete source' if mode=='text' else None)
   with patch.object(run,'INPUT_TOKENS',2280),patch.object(run,'api',return_value={'count':2281}) as api:
    with self.assertRaisesRegex(RuntimeError,'initial issue exceeds'):model.query(original)
   self.assertEqual(api.call_count,1)
   self.assertEqual(original[1]['content'],'Complete issue')
 def test_impossible_context_budget_is_rejected(self):
  with patch.dict(os.environ,{'SWE_CONTEXT_TOKENS':'4096','SWE_OUTPUT_TOKENS':'4096'}):
   candidate=importlib.util.module_from_spec(spec)
   with self.assertRaisesRegex(ValueError,'no input context'):spec.loader.exec_module(candidate)

if __name__=='__main__':unittest.main()
