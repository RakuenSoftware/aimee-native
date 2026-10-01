"""Previous GPU forward completes before native pin and table retirement."""
import importlib
import sys
from types import ModuleType,SimpleNamespace as NS
import unittest
from unittest.mock import patch


class AsyncOwnershipTests(unittest.TestCase):
    def test_gpu_completion_precedes_next_scheduler_update(self):
        events=[]
        class Event:
            def record(self,stream): events.append('record')
            def synchronize(self): events.append('synchronize')
        torch=ModuleType('torch');torch.cuda=NS(Event=Event,current_stream=lambda device:'stream')
        base=ModuleType('vllm.v1.worker.gpu_worker')
        class Worker:
            def execute_model(self,output):events.append('forward');return 'ok'
        base.Worker=Worker
        config=ModuleType('vllm.config');config.CUDAGraphMode=NS(NONE='none',PIECEWISE='piecewise')
        state=ModuleType('aimee_vllm.state')
        state.CURRENT=NS(begin=lambda output:events.append('begin'),
                         requests={'native':NS(store=object())},
                         refresh=lambda:events.append('refresh'))
        with patch.dict(sys.modules,{'torch':torch,'vllm':ModuleType('vllm'),
                     'vllm.v1':ModuleType('vllm.v1'),
                     'vllm.v1.worker':ModuleType('vllm.v1.worker'),
                     'vllm.v1.worker.gpu_worker':base,'vllm.config':config,
                     'aimee_vllm.state':state}):
            cached=sys.modules.pop('aimee_vllm.worker',None)
            prior=None
            try:
                worker=importlib.import_module('aimee_vllm.worker')
                prior=worker.state.CURRENT
                worker.state.CURRENT=state.CURRENT
                instance=worker.AimeeWorker.__new__(worker.AimeeWorker)
                instance.device='cuda:0'
                instance.vllm_config=NS(scheduler_config=NS(async_scheduling=True))
                instance._aimee_previous_forward=None
                output=NS(total_num_scheduled_tokens=1)
                self.assertEqual(instance.execute_model(output),'ok')
                self.assertEqual(instance.execute_model(output),'ok')
                instance.aimee_refresh_catalog()
            finally:
                if prior is not None or 'worker' in locals():
                    worker.state.CURRENT=prior
                sys.modules.pop('aimee_vllm.worker',None)
                if cached is not None:sys.modules['aimee_vllm.worker']=cached
        self.assertEqual(events,['begin','forward','record',
                                 'synchronize','begin','forward','record',
                                 'synchronize','refresh'])


if __name__=='__main__':unittest.main()
