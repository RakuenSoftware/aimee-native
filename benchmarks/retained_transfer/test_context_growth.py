import unittest
from context_growth import history_messages
class HistoryTests(unittest.TestCase):
 def test_current_scope_does_not_reinsert_prior_private_records(self):
  h=[{'task':'public task','answer':'public answer','record':'private learned rule'}]
  removed=history_messages(h,False)
  self.assertEqual(removed,[{'role':'user','content':'public task'},{'role':'assistant','content':'public answer'}])
  self.assertNotIn('private learned rule',str(removed))
  self.assertIn('private learned rule',history_messages(h,True)[0]['content'])
 def test_indirect_generated_information_is_retained(self):
  h=[{'task':'task','answer':'answer containing learned knowledge','record':'rule'}]
  self.assertEqual(history_messages(h,False)[1]['content'],h[0]['answer'])
if __name__=='__main__':unittest.main()
