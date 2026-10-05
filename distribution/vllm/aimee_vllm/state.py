"""Request ownership and publication pins; no record selection occurs here."""
from dataclasses import dataclass
import ctypes
import hashlib
import json
from pathlib import Path
import torch
from .store import PreparedStore
from .cache import DeviceCache

CURRENT = None

@dataclass(frozen=True)
class Pin:
    publication: str | None
    store: object = None

class State:
    def __init__(self, config, runner, device, rank, world):
        self.runner, self.device, self.rank, self.world = runner, device, rank, world
        self.requests = {}
        self.stores = {}
        self.tables = {}
        self.closed = False
        self.hybrid_hooks=[]
        self.hybrid_seed_events=0
        self.config = config
        raw_catalog = Path(config['catalog']).read_bytes()
        catalog = json.loads(raw_catalog)
        actual = hashlib.sha256((Path(config['model'])/'config.json').read_bytes()).hexdigest()
        if catalog['model_config_sha256'] != actual:
            raise RuntimeError('publication catalogue model mismatch')
        if catalog['recipient'] != config['recipient']:
            raise RuntimeError('publication catalogue recipient mismatch')
        lib = ctypes.CDLL(config['library'])
        self.catalog_digest = hashlib.sha256(raw_catalog).hexdigest()
        self.lib = lib
        from .model_adapter import ModelAdapter
        self.model_adapter = ModelAdapter(config, lib)
        lib.aimee_store_runtime_warmup.argtypes = [ctypes.c_int]
        lib.aimee_store_runtime_warmup.restype = ctypes.c_bool
        if not lib.aimee_store_runtime_warmup(device.index):
            raise RuntimeError('native runtime warmup failed')
        self.cache = DeviceCache(lib, config.get("device_memory_budget", 256 * 1024**2), device, rank, world, config.get("native_stage_telemetry",False))
        budget = config['host_memory_budget']
        try:
            for name, spec in catalog['publications'].items():
                store = PreparedStore(lib, {**spec, 'byte_budget': budget,'disk_backed':config.get('disk_backed',False),'lossless_transport':config.get('lossless_transport',True),'pipeline_transport':config.get('pipeline_transport',True),'device_budget':config.get('device_memory_budget',256*1024**2)})
                self.model_adapter.admit_store(store)
                store.prepare_plan(rank, world)
                self.stores[name] = store
                budget -= store.host_reservation_bytes()
                if budget < 0:
                    raise RuntimeError('publication catalogue exceeds memory budget')
        except BaseException:
            self.close()
            raise
        try:
            self.install_model_position_hook()
            if config.get('enable_hybrid_native') is True or any(getattr(s,'hybrid',None) is not None for s in self.stores.values()):
                self.install_hybrid_hooks()
        except BaseException:
            self.close()
            raise

    def install_model_position_hook(self):
        from vllm.forward_context import get_forward_context
        def position_before(module,args,kwargs):
            metadata=get_forward_context().attn_metadata
            if isinstance(metadata,dict):
                for item in metadata.values():
                    if getattr(item,'aimee_ids',None) is not None:
                        return self.model_adapter.positioned_arguments(args,kwargs,self.requests,item)
            return args,kwargs
        self.hybrid_hooks.append(self.runner.model.register_forward_pre_hook(position_before,with_kwargs=True))

    def install_hybrid_hooks(self):
        if self.config.get('enable_hybrid_native') is not True:
            raise RuntimeError('complete hybrid native serving disabled')
        serve=self.config.get('serve',{})
        if self.config.get('gguf_weights'):
            raise RuntimeError('complete hybrid prefixes currently require matching BF16 weights')
        if any(serve.get(k,False) for k in ('enable_prefix_caching','async_scheduling','enable_model_compilation','v2_model_runner','enable_piecewise_graphs')):
            raise RuntimeError('complete hybrid native serving requires eager synchronous V1')
        from vllm.model_executor.layers.mamba.gdn.qwen_gdn_linear_attn import QwenGatedDeltaNetAttention
        from vllm.model_executor.layers.mamba.mamba_utils import is_conv_state_dim_first
        from vllm.forward_context import get_forward_context
        from .hybrid import seed_layer
        import re
        config_raw=(Path(self.config['model'])/'config.json').read_bytes()
        model_config=json.loads(config_raw);c=model_config.get('text_config',model_config)
        expected={i for i,k in enumerate(c['layer_types']) if k=='linear_attention'}
        found=set()
        for _,module in self.runner.model.named_modules():
            if not isinstance(module,QwenGatedDeltaNetAttention):continue
            match=re.search(r'(?:^|\.)layers\.(\d+)\.',module.prefix)
            if match is None:raise RuntimeError('hybrid native layer identity unavailable')
            layer=int(match.group(1));found.add(layer)
            def before(module,args,layer=layer):
                metadata=get_forward_context().attn_metadata
                metadata=metadata.get(module.prefix) if isinstance(metadata,dict) else None
                if metadata is not None:
                    self.hybrid_seed_events+=seed_layer(module,layer,self.runner,self.requests,self.rank,self.world,metadata,is_conv_state_dim_first(),self.model_adapter)
            self.hybrid_hooks.append(module.register_forward_pre_hook(before))
        if found!=expected:raise RuntimeError('hybrid runtime layer coverage mismatch')
        from .hybrid import validate_model_identity
        for store in self.stores.values():
            if store.hybrid is not None:
                validate_model_identity(store.hybrid.spec,self.config['model'],self.config.get('model_revision'),self.config)
            if store.hybrid is not None and (store.hybrid.architecture!=c or store.hybrid.spec['model_config_sha256']!=hashlib.sha256(config_raw).hexdigest()):
                raise RuntimeError('hybrid publication architecture mismatch')

    def begin(self, scheduler_output):
        for rid in scheduler_output.finished_req_ids:
            self.requests.pop(rid, None)
        for req in scheduler_output.scheduled_new_reqs:
            extras = req.sampling_params.extra_args if req.sampling_params else None
            publication = (extras or {}).get('aimee_publication')
            expected = (extras or {}).get('aimee_catalog_digest')
            if expected is not None and expected != self.catalog_digest:
                raise RuntimeError('frontend/worker publication mismatch')
            old = self.requests.get(req.req_id)
            if old is not None:
                if old.publication != publication:
                    raise RuntimeError('cannot change memory within a pinned request')
                pin = old  # Preemption/resumption retains the exact admitted revision.
            else:
                if publication is not None and publication not in self.stores:
                    raise RuntimeError('native publication is unavailable to this serving instance')
                pin = Pin(publication, self.stores.get(publication))
            self.requests[req.req_id] = pin
        if scheduler_output.finished_req_ids or scheduler_output.scheduled_new_reqs:
            self.cache.ensure((p.store for p in self.requests.values() if p.store is not None), self.tables.clear)
        # Bound pointer-table cache at batch boundaries. Tensor references remain
        # alive through synchronous execution; graph/asynchronous modes rejected.
        if len(self.tables) > 256:
            self.tables.clear()

    def request_ids(self, common):
        indices = common.req_idx
        if hasattr(self.runner, 'req_states'):
            # V2 metadata carries stable request-state slots, not batch offsets.
            # Resolve them during forward, before execute_model_state is assigned.
            if indices is None:
                raise RuntimeError('native V2 attention is missing request slots')
            slots = {index: rid for rid, index in
                     self.runner.req_states.req_id_to_index.items()}
            ids = tuple(slots.get(int(i)) for i in indices[:common.num_reqs])
        else:
            batch = self.runner.input_batch.req_ids
            if indices is None:
                ids = tuple(batch[:common.num_reqs])
            else:
                ids = tuple(batch[int(i)] for i in indices[:common.num_reqs])
        if len(ids) != common.num_reqs or len(set(ids)) != len(ids):
            raise RuntimeError('native request/batch mapping mismatch')
        for rid in ids:
            if rid not in self.requests:
                raise RuntimeError('scheduled native request is not pinned')
        return ids

    def upstream_only_without_slots(self, common):
        # Hybrid-model kernel warmup can schedule synthetic requests before V2
        # has populated request-state slots. They have no native publication;
        # standard attention is sufficient. Never bypass slot checks while a
        # native publication is pinned by any request.
        return (common.req_idx is None and bool(self.requests)
                and all(pin.store is None for pin in self.requests.values()))

    def memory_table(self, ids, layer, dtype, heads, width):
        selections = tuple(self.requests[r] for r in ids)
        if not any(s.store is not None for s in selections):
            return None
        cache_key = (tuple(s.store.uid if s.store is not None else None for s in selections), layer, dtype, heads, width)
        if cache_key in self.tables:
            return self.tables[cache_key]
        keys, values, lengths = [], [], []
        owners = []
        for selected in selections:
            if selected.store is None:
                keys.append(0); values.append(0); lengths.append(0)
                continue
            banks = selected.store.resident(self.device, self.rank, self.world)
            k, v = banks[(layer, False)], banks[(layer, True)]
            if k.shape != v.shape or k.shape[0] != heads or k.shape[2] != width or k.dtype != dtype:
                raise RuntimeError('native attention bank geometry/dtype mismatch')
            keys.append(k.data_ptr()); values.append(v.data_ptr()); lengths.append(k.shape[1])
            owners.extend((k,v))
        tables = tuple(torch.tensor(a, dtype=t, device=self.device) for a,t in
                       [(keys,torch.uint64),(values,torch.uint64),(lengths,torch.int32)])
        # owners pin storage while GPU pointer tables are usable.
        result = (*tables, owners)
        self.tables[cache_key] = result
        return result

    def refresh(self):
        """Explicit control-plane operation through the supported worker RPC.
        New requests see the new catalogue; existing requests retain their pin.
        No file checks or integrity scans are added to attention execution.
        """
        config = self.config
        raw_catalog = Path(config['catalog']).read_bytes()
        catalog = json.loads(raw_catalog)
        actual = hashlib.sha256((Path(config['model'])/'config.json').read_bytes()).hexdigest()
        if catalog['model_config_sha256'] != actual or catalog['recipient'] != config['recipient']:
            raise RuntimeError('replacement publication identity mismatch')
        live = {s.uid:s for s in self.cache.resident.values()}
        live.update({s.uid:s for s in self.stores.values()})
        live.update({p.store.uid:p.store for p in self.requests.values() if p.store is not None})
        disk_backed=config.get('disk_backed',False)
        remaining = config['host_memory_budget'] - sum(s.host_reservation_bytes() for s in live.values())
        admitted = {};created=[]
        try:
            for name,spec in catalog['publications'].items():
                previous = self.stores.get(name)
                if previous is not None and all(previous.spec.get(k)==v for k,v in spec.items()):
                    admitted[name] = previous
                    continue
                if remaining <= 0: raise RuntimeError('native publication replacement exceeds pinned memory budget')
                store = PreparedStore(self.lib,{**spec,'byte_budget':remaining,'disk_backed':disk_backed,'lossless_transport':config.get('lossless_transport',True),'pipeline_transport':config.get('pipeline_transport',True),'device_budget':config.get('device_memory_budget',256*1024**2)})
                created.append(store)
                self.model_adapter.admit_store(store)
                if store.hybrid is not None:
                    if not getattr(self,'hybrid_hooks',None):raise RuntimeError('hybrid publication requires a configured hybrid worker')
                    model_config=json.loads((Path(config['model'])/'config.json').read_bytes())
                    if store.hybrid.spec['model_config_sha256']!=actual or store.hybrid.architecture!=model_config.get('text_config',model_config):raise RuntimeError('hybrid replacement model mismatch')
                if store.hybrid is not None:
                    from .hybrid import validate_model_identity
                    validate_model_identity(store.hybrid.spec,self.config['model'],self.config.get('model_revision'),self.config)
                store.prepare_plan(self.rank, self.world)
                admitted[name]=store
                remaining -= store.host_reservation_bytes()
            self.tables.clear()
            if not self.requests:
                previous_stages=getattr(self.cache,'stages',None)
                self.cache.close()
                self.cache = DeviceCache(self.lib, config.get("device_memory_budget",256*1024**2), self.device,self.rank,self.world,config.get("native_stage_telemetry",False))
                if previous_stages is not None:self.cache.stages=previous_stages
            self.stores = admitted
            self.catalog_digest = hashlib.sha256(raw_catalog).hexdigest()
        except BaseException:
            for store in created: store.close()
            raise
        return {'publications':len(admitted),'pinned_requests':len(self.requests),'catalog_digest':self.catalog_digest}

    def close(self):
        for hook in getattr(self,'hybrid_hooks',[]):hook.remove()
        self.hybrid_hooks=[]
        self.tables.clear()
        if hasattr(self, "cache"): self.cache.close()
        self.requests.clear()
        for store in self.stores.values(): store.close()
        self.stores.clear()
        self.closed = True
