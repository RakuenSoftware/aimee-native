import unittest
from source_experience import accept_success,patch_command,promote,successful_commands,render_success,failure_evidence,render_format_failure

class SourceExperience(unittest.TestCase):
 def setUp(self):
  self.task={'instance_id':'fixture','base_commit':'abc'}
  self.patch='diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n'
  self.row={'resolved':True,'model_patch':self.patch,'arm':'source'}
 def test_replay_rejects_wrong_edit_and_preserves_complete_patch(self):
  trace={'messages':[{'role':'assistant','extra':{'actions':[{'command':'sed -i wrong a.py'}]}},{'role':'user','extra':{'returncode':0}}]}
  commands=[]
  def replay(c):
   commands.append(c);return {'returncode':0,'patch':'wrong' if len(commands)==1 else self.patch}
  e=accept_success(self.task,self.row,trace,replay)
  self.assertEqual(e['command'],patch_command(self.patch));self.assertIn(self.patch,render_success(e))
  self.assertFalse(e['replay_trials'][0]['matches_successful_patch'])
 def test_failed_execution_is_not_a_successful_command(self):
  trace={'messages':[{'role':'assistant','extra':{'actions':[{'command':'bad'}]}},{'role':'user','extra':{'returncode':1}}]}
  self.assertEqual(successful_commands(trace),[])
 def test_failed_attempt_cannot_replace_accepted_experience(self):
  old={'scope':self.task,'kind':'accepted_success','command':'good'}
  self.assertIs(promote(old,{'scope':self.task,'kind':'failed_attempt'}),old)
 def test_scope_mismatch_rejected(self):
  with self.assertRaises(ValueError):promote({'scope':self.task,'kind':'accepted_success'},{'scope':{},'kind':'failed_attempt'})
 def test_no_acceptance_without_successful_replay(self):
  with self.assertRaises(ValueError):accept_success(self.task,self.row,{},lambda c:{'returncode':1,'patch':self.patch})
 def test_no_acceptance_from_failure_boolean(self):
  with self.assertRaises(ValueError):accept_success(self.task,dict(self.row,resolved=False),{},lambda c:None)

class FormatEvidence(unittest.TestCase):
 def test_rejected_response_retains_feedback_without_treating_it_as_execution(self):
  feedback='Return exactly one fenced bash command. Your response exceeded the output limit. Use one shorter command.'
  trace={'messages':[{'role':'assistant','content':'thought\n'*128,'extra':{'finish_reason':'length'}},
                     {'role':'user','content':feedback}]}
  e=failure_evidence({'instance_id':'x','base_commit':'b'},{'arm':'control','resolved':False},trace)
  self.assertEqual(e['observations'],[])
  self.assertEqual(e['format_failures'][0]['response'],trace['messages'][0]['content'])
  rendered=render_format_failure(e)
  self.assertIn(feedback,rendered)
  self.assertIn('before any command executed',rendered)
  self.assertNotIn('thought',rendered)
 def test_tool_output_cannot_masquerade_as_parser_feedback(self):
  trace={'messages':[{'role':'assistant','content':'cmd','extra':{'actions':[{'command':'bad'}]}},
       {'role':'user','content':'Return exactly one fenced bash command.','extra':{'returncode':1}}]}
  e=failure_evidence({'instance_id':'x','base_commit':'b'},{'arm':'control','resolved':False},trace)
  self.assertEqual(e['format_failures'],[])
  self.assertEqual(len(e['observations']),1)

if __name__=='__main__':unittest.main()
