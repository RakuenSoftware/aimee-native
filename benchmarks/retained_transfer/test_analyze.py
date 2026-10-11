import unittest
import numpy as np
from analyze import holm,intervals,superiority

class StatisticsTests(unittest.TestCase):
    def test_holm_keeps_unavailable_hypotheses(self):
        adjusted=holm({'a':.01,'b':.04,'c':None})
        self.assertAlmostEqual(adjusted['a'],.03)
        self.assertAlmostEqual(adjusted['b'],.08)
        self.assertIsNone(adjusted['c'])
    def test_no_effect_does_not_become_learning(self):
        self.assertEqual(superiority([0]*60),1)
        ci,draws=intervals([0]*60,['a']*20+['b']*20+['c']*20)
        self.assertEqual(ci,[0,0]);self.assertEqual(len(draws),10000)
    def test_cluster_sampling_is_reproducible(self):
        v=[i/60 for i in range(60)];languages=['a']*20+['b']*20+['c']*20
        ci,a=intervals(v,languages);other,b=intervals(v,languages)
        self.assertEqual(ci,other);np.testing.assert_array_equal(a,b)

if __name__=='__main__':unittest.main()
