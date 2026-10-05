import unittest
from router import fit,route,evaluate
C={'model_revision':'fixture','representation':'query-post-rotary','layer':3,'pooling':'mean-heads-last-token','position':'conversation-absolute','width':2}
class RouterTests(unittest.TestCase):
    def router(self):return fit([{'partition':'a','features':[1.,0.]},{'partition':'b','features':[0.,1.]}],C)
    def test_candidates_are_bounded_and_restrict_to_current_partitions(self):
        hint=route(self.router(),[1.,0.],C,['b'],budget=1)
        self.assertTrue(hint['fallback_required'])
        hint=route(self.router(),[1.,.2],C,['a','b'],budget=1)
        self.assertEqual(hint['partitions'],['a']);self.assertNotIn('content',hint)
    def test_contract_mismatch_and_deleted_partitions_abstain(self):
        self.assertEqual(route(self.router(),[1.,0.],dict(C,model_revision='replacement'),['a'])['reason'],'representation_mismatch')
        self.assertEqual(route(self.router(),[1.,0.],C,[])['reason'],'no_current_candidates')
    def test_ambiguous_address_has_measured_fallback(self):
        self.assertTrue(route(self.router(),[1.,1.],C,['a','b'],min_margin=.1)['fallback_required'])
    def test_malformed_features_and_budget_refused(self):
        for f in ([True,0.],[float('nan'),1.],[0.,0.],[1.]):
            with self.assertRaises(ValueError):route(self.router(),f,C,['a'])
        with self.assertRaises(ValueError):route(self.router(),[1.,0.],C,['a'],budget=0)
    def test_holdout_family_leakage_refused(self):
        samples=[{'split':split,'family':'same','partition':'a','features':[1.,0.]} for split in ('development','heldout')]
        with self.assertRaisesRegex(ValueError,'leakage'):evaluate({'contract':C,'samples':samples,'available_partitions':['a']},1,.1,0.)
    def test_unknown_partition_stays_a_miss(self):
        samples=[{'split':'development','family':'train','partition':'a','features':[1.,0.]},
                 {'split':'heldout','family':'unknown','partition':'unseen','features':[1.,0.]}]
        report,_=evaluate({'contract':C,'samples':samples,'available_partitions':['a','unseen']},1,.1,0.)
        self.assertEqual(report['candidate_hits'],0)
