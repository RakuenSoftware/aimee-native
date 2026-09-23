import unittest
from procedure_gate import choose,validate
class GateTests(unittest.TestCase):
 def setUp(self):self.examples=[dict(input=x,output=5*x+15) for x in (1,4,9)]
 def test_observed_regression_rejected(self):
  d=choose('Multiply the input by 5 and add 10.','Multiply the input by 5 and add 15.',self.examples)
  self.assertFalse(d['accepted']);self.assertEqual(d['selected'],d['previous'])
 def test_correct_revision_accepted(self):
  d=choose('Multiply the input by 5 and add 15.','Multiply the input by 5 and add 5.',self.examples)
  self.assertTrue(d['accepted']);self.assertEqual(d['selected'],d['candidate'])
 def test_subtraction(self):
  self.assertTrue(validate('Multiply by 5 then subtract 2.',[dict(input=4,output=18)])['accepted'])
 def test_unknown_syntax_not_executed(self):
  self.assertFalse(validate('__import__("os").system("false")',self.examples)['accepted'])
 def test_matching_one_example_is_not_enough(self):
  self.assertFalse(validate('Multiply by 10 and add 10.',self.examples)['accepted'])
if __name__=='__main__':unittest.main()
