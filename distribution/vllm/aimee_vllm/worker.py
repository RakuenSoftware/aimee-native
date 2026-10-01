"""Supported worker_cls subclass. Upstream classes/functions are never replaced."""
import json
import os
import torch
from vllm.v1.worker.gpu_worker import Worker
from vllm.config import CUDAGraphMode
from . import state

class AimeeWorker(Worker):
    def init_device(self):
        super().init_device()
        cfg = self.vllm_config
        if self.use_v2_model_runner:
            raise RuntimeError('native memory requires VLLM_USE_V2_MODEL_RUNNER=0')
        graph_mode=cfg.compilation_config.cudagraph_mode
        if graph_mode not in (CUDAGraphMode.NONE,CUDAGraphMode.PIECEWISE):
            raise RuntimeError('full native-attention graph capture is not supported')
        if graph_mode == CUDAGraphMode.PIECEWISE and not self._aimee_piecewise_enabled():
            raise RuntimeError('native piecewise graph configuration mismatch')
        if cfg.cache_config.enable_prefix_caching != self._aimee_prefix_enabled():
            raise RuntimeError('native prefix-cache configuration mismatch')
        if cfg.scheduler_config.async_scheduling != self._aimee_async_enabled():
            raise RuntimeError('native asynchronous scheduling configuration mismatch')
        if cfg.speculative_config is not None:
            raise RuntimeError('speculative scheduling is not yet supported')
        if cfg.parallel_config.pipeline_parallel_size != 1:
            raise RuntimeError('pipeline parallel native memory is not yet supported')
        self._aimee_previous_forward = None

    def load_model(self, *, load_dummy_weights=False):
        super().load_model(load_dummy_weights=load_dummy_weights)
        from vllm.distributed import get_tensor_model_parallel_rank, get_tensor_model_parallel_world_size
        with open(os.environ['AIMEE_VLLM_CONFIG']) as f:
            config = json.load(f)
        if str(self.vllm_config.model_config.model) != config['model']:
            raise RuntimeError('native publication model path mismatch')
        state.CURRENT = state.State(config, self.model_runner, self.device,
                                    get_tensor_model_parallel_rank(), get_tensor_model_parallel_world_size())

    def _aimee_prefix_enabled(self):
        with open(os.environ['AIMEE_VLLM_CONFIG']) as f:
            config=json.load(f)
        return config.get('serve',{}).get('enable_prefix_caching',False) is True

    def _aimee_async_enabled(self):
        with open(os.environ['AIMEE_VLLM_CONFIG']) as f:
            config=json.load(f)
        return config.get('serve',{}).get('async_scheduling',False) is True

    def _aimee_piecewise_enabled(self):
        with open(os.environ['AIMEE_VLLM_CONFIG']) as f:
            config=json.load(f)
        return config.get('serve',{}).get('enable_piecewise_graphs',False) is True

    def execute_model(self, scheduler_output):
        if state.CURRENT is None:
            raise RuntimeError('native memory worker is not initialized')
        # Scheduler output can advance while the previous GPU forward is still
        # running. Wait before retiring pins or evicting pointer-table owners.
        self._aimee_wait_for_forward()
        state.CURRENT.begin(scheduler_output)
        result=super().execute_model(scheduler_output)
        if (self.vllm_config.scheduler_config.async_scheduling
            and scheduler_output.total_num_scheduled_tokens
            and any(pin.store is not None for pin in state.CURRENT.requests.values())):
            event=torch.cuda.Event()
            event.record(torch.cuda.current_stream(self.device))
            self._aimee_previous_forward=event
        return result

    def _aimee_wait_for_forward(self):
        previous=self._aimee_previous_forward
        if previous is not None:
            previous.synchronize()
            self._aimee_previous_forward=None

    def aimee_refresh_catalog(self):
        if state.CURRENT is None:
            raise RuntimeError('native memory worker is not initialized')
        self._aimee_wait_for_forward()
        return state.CURRENT.refresh()

    def aimee_cache_stats(self):
        if state.CURRENT is None:
            raise RuntimeError('native memory worker is not initialized')
        result=dict(state.CURRENT.cache.stats)
        result['catalogue_payload_bytes']=sum(s.metadata['bytes'] for s in state.CURRENT.stores.values())
        result['disk_backed']=state.CURRENT.config.get('disk_backed',False)
        # Explicit control-plane telemetry; never executed inside attention.
        resident=0;native_mapping=False
        with open('/proc/self/smaps') as maps:
            for line in maps:
                if '-' in line.split()[0]:native_mapping=line.rstrip().endswith('/compact.pack')
                elif native_mapping and line.startswith('Rss:'):resident+=int(line.split()[1])*1024
        result['mapped_payload_rss_bytes']=resident
        import torch
        free,total=torch.cuda.mem_get_info(self.device)
        result['device']={
            'total_bytes':total, 'free_bytes':free,
            'driver_used_bytes':total-free,
            'torch_allocated_bytes':torch.cuda.memory_allocated(self.device),
            'torch_reserved_bytes':torch.cuda.memory_reserved(self.device),
            'torch_peak_allocated_bytes':torch.cuda.max_memory_allocated(self.device),
            'torch_peak_reserved_bytes':torch.cuda.max_memory_reserved(self.device),
        }
        # Includes model weights, KV cache, native banks, pointer tables and
        # temporary allocations tracked by the allocator. Driver use additionally
        # includes non-Torch allocations and other processes on this GPU.
        with open('/proc/self/status') as status:
            fields={line.split(':',1)[0]:line.split(':',1)[1].strip()
                    for line in status if ':' in line}
        result['process']={key:int(fields[key].split()[0])*1024
                           for key in ('VmRSS','VmHWM') if key in fields}
        return result
