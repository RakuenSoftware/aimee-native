import unittest
import numpy as np
from analyze import holm,intervals,superiority,acquired_diagnostics,MODELS,ARMS

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
    def test_fidelity_excludes_empty_record_fallbacks(self):
        grouped={}
        for model in MODELS:
            for arm in ARMS:
                for fid in ('acquired','missing'):
                    score=int(fid=='missing' or arm=='Text')
                    grouped[model,arm,fid]=[{'repeat':r,'input_id':fid+'-0','score':score,
                        'output':'correct' if score else 'wrong','ttft_ms':10,
                        'end_to_end_ms':20,'prompt_tokens':30,'prefill_tokens':30} for r in range(3)]
        records={'acquired':{'canonical_record_id':'id','content_sha256':'hash',
                            'validation':{'matches':8,'total':8}}}
        info={f:{'language':'one'} for f in ('acquired','missing')}
        rules,fidelity,costs=acquired_diagnostics(grouped,records,set(info),info)
        self.assertEqual(len(rules),4)
        self.assertTrue(all(x['mean_native_minus_text']==-1 for x in fidelity))
        self.assertTrue(all(x['admitted_eligible_families']==1 for x in fidelity))
        self.assertTrue(all(x['family_clustered_ci'] is None for x in fidelity))
        self.assertTrue(all(x['requests']==3 for x in costs))

    def test_cluster_sampling_is_reproducible(self):
        v=[i/60 for i in range(60)];languages=['a']*20+['b']*20+['c']*20
        ci,a=intervals(v,languages);other,b=intervals(v,languages)
        self.assertEqual(ci,other);np.testing.assert_array_equal(a,b)

if __name__=='__main__':unittest.main()
