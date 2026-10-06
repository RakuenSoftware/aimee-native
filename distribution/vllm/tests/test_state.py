import unittest
from unittest.mock import patch
import tempfile,json,hashlib
from pathlib import Path
from types import SimpleNamespace as NS
from aimee_vllm.state import State,Pin

class FakeStore:
    def activate(self,*args): return {}
class StateTests(unittest.TestCase):
    def test_q4_hooks_require_bound_weights_and_preserve_runner_guards(self):
        runtime=State.__new__(State)
        runtime.config={'enable_hybrid_native':True,'gguf_weights':'/checkpoint.gguf'}
        with self.assertRaisesRegex(ValueError,'bound Q4_K_M'):
            runtime.install_hybrid_hooks()
        runtime.config.update(gguf_weights_sha256='a'*64,gguf_weight_profile='Q4_K_M',serve={'async_scheduling':True})
        with patch('torch.cuda.get_device_capability',return_value=(11,0)),self.assertRaisesRegex(RuntimeError,'eager'):
            runtime.install_hybrid_hooks()

    def test_enabled_hybrid_hooks_are_installed_with_empty_catalogue(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'config.json').write_bytes(b'{}')
            catalog=root/'catalog.json'
            catalog.write_text(json.dumps({'model_config_sha256':hashlib.sha256(b'{}').hexdigest(),
                                           'recipient':'approved','publications':{}}))
            config={'model':str(root),'catalog':str(catalog),'recipient':'approved',
                    'library':'unused','host_memory_budget':1024,'enable_hybrid_native':True}
            with patch('aimee_vllm.state.ctypes.CDLL') as library,patch('aimee_vllm.state.DeviceCache'),patch.object(State,'install_hybrid_hooks') as hooks, patch.object(State,'install_model_position_hook'), patch('aimee_vllm.model_adapter.ModelAdapter'):
                library.return_value.aimee_store_runtime_warmup.return_value=True
                state=State(config,NS(),NS(index=0),0,1)
                hooks.assert_called_once()
                self.assertEqual(state.stores,{})
                state.close()
    def test_refresh_preserves_requested_stage_measurements(self):
        from aimee_vllm.telemetry import Stages
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'config.json').write_bytes(b'{}')
            catalog=root/'catalog.json';catalog.write_text(json.dumps({'recipient':'approved','model_config_sha256':hashlib.sha256(b'{}').hexdigest(),'publications':{}}))
            state=State.__new__(State)
            state.config={'model':str(root),'catalog':str(catalog),'recipient':'approved','host_memory_budget':1024,'native_stage_telemetry':True}
            state.requests={};state.stores={};state.tables={};state.lib=object();state.device='cpu';state.rank=0;state.world=1
            state.cache=NS(resident={},close=lambda:None,stages=Stages(True))
            with state.cache.stages.measure('before_refresh'):pass
            def cache(lib,budget,device,rank,world,telemetry=False):return NS(stages=Stages(telemetry))
            with patch('aimee_vllm.state.DeviceCache',side_effect=cache):state.refresh()
            with state.cache.stages.measure('after_refresh'):pass
            stages=state.cache.stages.snapshot()['stages']
            self.assertEqual(stages['after_refresh_success']['count'],1)
            self.assertEqual(stages['before_refresh_success']['count'],1)

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
    def test_missing_v2_slots_bypass_only_publication_free_warmup(self):
        s=self.state()
        s.runner=NS(req_states=NS(req_id_to_index={'warmup':0}))
        s.begin(self.output([('warmup',None)]))
        no_slots=NS(req_idx=None,num_reqs=1)
        self.assertTrue(s.upstream_only_without_slots(no_slots))
        self.assertFalse(s.upstream_only_without_slots(NS(req_idx=[0],num_reqs=1)))
        s.begin(NS(finished_req_ids={'warmup'},scheduled_new_reqs=[]))
        s.begin(self.output([('native','approved')]))
        self.assertFalse(s.upstream_only_without_slots(no_slots))
        with self.assertRaisesRegex(RuntimeError,'missing request slots'):
            s.request_ids(no_slots)
if __name__=='__main__':unittest.main()
