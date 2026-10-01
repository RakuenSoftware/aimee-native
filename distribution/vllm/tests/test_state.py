import unittest
from types import SimpleNamespace as NS
from aimee_vllm.state import State,Pin

class FakeStore:
    def activate(self,*args): return {}
class StateTests(unittest.TestCase):
    def state(self):
        s=State.__new__(State);s.requests={};s.tables={};s.stores={'approved':FakeStore()}
        s.device='cpu';s.rank=0;s.world=1
        s.cache=NS(ensure=lambda stores,clear: None)
        s.runner=NS(input_batch=NS(req_ids=['b','a']))
        return s
    def output(self,ids):
        return NS(finished_req_ids=set(),scheduled_new_reqs=[NS(req_id=r,sampling_params=NS(extra_args={'aimee_publication':p})) for r,p in ids])
    def test_reorder_and_retirement_preserve_identity(self):
        s=self.state();s.begin(self.output([('a','approved'),('b',None)]))
        self.assertEqual(s.request_ids(NS(req_idx=None,num_reqs=2)),('b','a'))
        self.assertEqual(s.request_ids(NS(req_idx=[1,0],num_reqs=2)),('a','b'))
        s.begin(NS(finished_req_ids={'a'},scheduled_new_reqs=[]));self.assertNotIn('a',s.requests)
    def test_unapproved_selection_and_mid_request_rebinding_fail(self):
        s=self.state()
        with self.assertRaises(RuntimeError):s.begin(self.output([('a','../other-recipient')]))
        s.begin(self.output([('a','approved')]))
        with self.assertRaises(RuntimeError):s.begin(self.output([('a',None)]))
    def test_resumed_request_keeps_revision_after_replacement_and_withdrawal(self):
        s=self.state();s.begin(self.output([('a','approved')]))
        original=s.requests['a'].store
        s.stores['approved']=FakeStore()
        s.begin(self.output([('a','approved'),('b','approved')]))
        self.assertIs(s.requests['a'].store,original)
        self.assertIsNot(s.requests['b'].store,original)
        s.stores.clear();s.begin(self.output([('a','approved')]))
        self.assertIs(s.requests['a'].store,original)
        with self.assertRaises(RuntimeError):s.begin(self.output([('new','approved')]))
    def test_missing_request_fails_instead_of_borrowing_another_bank(self):
        s=self.state();s.begin(self.output([('a','approved')]))
        with self.assertRaises(RuntimeError):s.request_ids(NS(req_idx=None,num_reqs=2))
    def test_v2_physical_slots_resolve_during_forward(self):
        s=self.state();s.begin(self.output([('a','approved'),('b',None)]))
        s.runner=NS(req_states=NS(req_id_to_index={'a':7,'b':2}))
        self.assertEqual(s.request_ids(NS(req_idx=[2,7],num_reqs=2)),('b','a'))
        with self.assertRaisesRegex(RuntimeError,'not pinned'):
            s.request_ids(NS(req_idx=[2,9],num_reqs=2))
        with self.assertRaisesRegex(RuntimeError,'missing request slots'):
            s.request_ids(NS(req_idx=None,num_reqs=2))
        with self.assertRaisesRegex(RuntimeError,'mapping mismatch'):
            s.request_ids(NS(req_idx=[2,2],num_reqs=2))
if __name__=='__main__':unittest.main()
