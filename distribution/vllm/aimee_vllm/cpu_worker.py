"""Explicit vLLM CPU worker subclass; GPU worker and upstream code unchanged."""
import json,os
import torch
from vllm.v1.worker.cpu_worker import CPUWorker
from vllm.v1.attention.backends.registry import AttentionBackendEnum,register_backend
from . import cpu_state as state
register_backend(AttentionBackendEnum.CUSTOM,'aimee_vllm.cpu_backend.AimeeCPUBackend')
class AimeeCPUWorker(CPUWorker):
    def load_model(self,*args,**kwargs):
        config=json.loads(open(os.environ['AIMEE_VLLM_CPU_CONFIG']).read())
        cfg=self.vllm_config
        if str(cfg.model_config.model)!=config['model'] or cfg.model_config.dtype!=torch.float32:raise RuntimeError('CPU serving profile mismatch')
        if cfg.parallel_config.tensor_parallel_size!=1 or cfg.parallel_config.pipeline_parallel_size!=1 or cfg.scheduler_config.async_scheduling or cfg.cache_config.enable_prefix_caching or cfg.speculative_config is not None:raise RuntimeError('CPU native profile requires synchronous eager single-rank execution without prefix caching')
        state.CURRENT=state.CPUState(config,self.model_runner)
        super().load_model(*args,**kwargs)
        state.CURRENT.versions=[(id(p),p._version) for p in self.model_runner.model.parameters()]
        if any(p.device.type!='cpu' for p in self.model_runner.model.parameters()):raise RuntimeError('CPU native model escaped CPU')
        self._aimee_position_hook=self.model_runner.model.register_forward_pre_hook(state.CURRENT.shift,with_kwargs=True)
    def execute_model(self,scheduler_output):
        if state.CURRENT is None:raise RuntimeError('CPU native worker unavailable')
        state.CURRENT.begin(scheduler_output)
        return super().execute_model(scheduler_output)
    def aimee_cpu_quiesce(self):
        if state.CURRENT.capture is not None:raise RuntimeError("CPU capture still active")
        state.CURRENT.pins.clear();state.CURRENT.shadow.clear()
        return {"pinned_requests":0}
    def aimee_cpu_arm_capture(self,*args):return state.CURRENT.arm(*args)
    def aimee_cpu_finish_capture(self):return state.CURRENT.finish()
    def aimee_cpu_metrics(self):return state.CURRENT.audit()
