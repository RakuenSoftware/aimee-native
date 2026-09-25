"""Supported worker_cls subclass. Upstream classes/functions are never replaced."""
import json
import os
from vllm.v1.worker.gpu_worker import Worker
from . import state

class AimeeWorker(Worker):
    def init_device(self):
        super().init_device()
        cfg = self.vllm_config
        if self.use_v2_model_runner:
            raise RuntimeError('Aimee currently requires VLLM_USE_V2_MODEL_RUNNER=0')
        if not cfg.model_config.enforce_eager:
            raise RuntimeError('native memory graph capture has not been validated; use enforce_eager')
        if cfg.cache_config.enable_prefix_caching:
            raise RuntimeError('text prefix caching must be disabled until memory-aware cache identity is supported')
        if cfg.scheduler_config.async_scheduling or cfg.speculative_config is not None:
            raise RuntimeError('asynchronous/speculative scheduling is not yet supported')
        if cfg.parallel_config.pipeline_parallel_size != 1:
            raise RuntimeError('pipeline parallel native memory is not yet supported')

    def load_model(self, *, load_dummy_weights=False):
        super().load_model(load_dummy_weights=load_dummy_weights)
        from vllm.distributed import get_tensor_model_parallel_rank, get_tensor_model_parallel_world_size
        with open(os.environ['AIMEE_VLLM_CONFIG']) as f:
            config = json.load(f)
        if str(self.vllm_config.model_config.model) != config['model']:
            raise RuntimeError('native publication model path mismatch')
        state.CURRENT = state.State(config, self.model_runner, self.device,
                                    get_tensor_model_parallel_rank(), get_tensor_model_parallel_world_size())

    def execute_model(self, scheduler_output):
        if state.CURRENT is None:
            raise RuntimeError('native memory worker is not initialized')
        state.CURRENT.begin(scheduler_output)
        return super().execute_model(scheduler_output)

    def aimee_refresh_catalog(self):
        if state.CURRENT is None:
            raise RuntimeError('native memory worker is not initialized')
        return state.CURRENT.refresh()
