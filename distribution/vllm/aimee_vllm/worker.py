"""Supported worker_cls subclass. Upstream classes/functions are never replaced."""
import json
import os
import torch
from vllm.v1.worker.gpu_worker import Worker
from vllm.config import CUDAGraphMode
from vllm.v1.worker.gpu.model_states.mamba_hybrid import MambaHybridModelState
from . import state


def require_v2_request_slots(runner, enabled):
    # vLLM 0.30's hybrid model state omits req_idx from attention metadata even
    # for live requests. Without those slots, native banks cannot be assigned
    # to the right request safely. The V1 runner remains supported.
    if enabled and isinstance(runner.model_state, MambaHybridModelState):
        raise RuntimeError(
            'native V2 hybrid attention does not expose request slots; '
            'set v2_model_runner=false for this model'
        )

class AimeeWorker(Worker):
    def init_device(self):
        super().init_device()
        cfg = self.vllm_config
        if self.use_v2_model_runner != self._aimee_v2_enabled():
            raise RuntimeError('native V2 model-runner configuration mismatch')
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
        require_v2_request_slots(self.model_runner, self.use_v2_model_runner)
        from vllm.distributed import get_tensor_model_parallel_rank, get_tensor_model_parallel_world_size
        with open(os.environ['AIMEE_VLLM_CONFIG']) as f:
            config = json.load(f)
        if str(self.vllm_config.model_config.model) != config['model']:
            raise RuntimeError('native publication model path mismatch')
        if config.get('quantization') and torch.cuda.get_device_capability(self.device)!=(12,0):
            raise RuntimeError('this FP8 native profile requires Blackwell SM120')
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

    def _aimee_v2_enabled(self):
        with open(os.environ['AIMEE_VLLM_CONFIG']) as f:
            config=json.load(f)
        return config.get('serve',{}).get('v2_model_runner',False) is True

    def execute_model(self, scheduler_output):
        if state.CURRENT is None:
            raise RuntimeError('native memory worker is not initialized')
        # Scheduler output can advance while the previous GPU forward is still
        # running. Wait before retiring pins or evicting pointer-table owners.
        self._aimee_wait_for_forward()
        from . import capture_session as capture
        if capture.CURRENT is not None:capture.CURRENT.begin(scheduler_output)
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
        result["hybrid_seed_events"]=state.CURRENT.hybrid_seed_events
        result["host_stages"]=state.CURRENT.cache.stages.snapshot()
        result['catalogue_payload_bytes']=sum(s.metadata['bytes'] for s in state.CURRENT.stores.values())
        result['catalogue_hybrid_payload_bytes']=sum(len(s.hybrid.data) for s in state.CURRENT.stores.values() if s.hybrid is not None)
        result['catalogue_host_admission_bytes']=sum(s.host_reservation_bytes() for s in state.CURRENT.stores.values())
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

    def aimee_capture_begin(self, tokens, context, destination, exclusive_control=False):
        from . import capture_session as capture
        if capture.CURRENT is not None:raise RuntimeError('capture already active')
        from .capture import PrefixCapture
        config = self._aimee_capture_config(exclusive_control)
        capture.CURRENT=PrefixCapture(config,self.model_runner,tokens,context,destination)
        return {'state':'armed'}

    def aimee_capture_finish(self):
        from . import capture_session as capture
        if capture.CURRENT is None:raise RuntimeError('capture is not active')
        try:return capture.CURRENT.finish()
        finally:
            capture.CURRENT.close();capture.CURRENT=None

    def _aimee_capture_config(self, exclusive_control):
        config = state.CURRENT.config
        if exclusive_control:
            if config.get('native_preparation_enabled') is not True:
                raise RuntimeError('enrolled native preparation is disabled')
            config = dict(config, offline_prefix_capture=True)
        return config

    def aimee_attention_capture_begin(self, tokens, text, destination, exclusive_control=False):
        # text is a legacy rendered string or the versioned {text, composition}
        # envelope. Keep this RPC unannotated so Cython accepts both wire shapes.
        from . import capture_session as capture
        from .attention_capture import AttentionPrefixCapture
        if capture.CURRENT is not None:raise RuntimeError('capture already active')
        config = self._aimee_capture_config(exclusive_control)
        capture.CURRENT=AttentionPrefixCapture(config,self.model_runner,tokens,text,destination)
        return {'state':'armed'}
