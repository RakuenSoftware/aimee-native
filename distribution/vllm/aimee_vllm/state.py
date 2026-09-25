"""Request ownership and publication pins; no record selection occurs here."""
from dataclasses import dataclass
import ctypes
import hashlib
import json
from pathlib import Path
import torch
from .store import PreparedStore

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
        self.config = config
        catalog = json.loads(Path(config['catalog']).read_text())
        actual = hashlib.sha256((Path(config['model'])/'config.json').read_bytes()).hexdigest()
        if catalog['model_config_sha256'] != actual:
            raise RuntimeError('publication catalogue model mismatch')
        if catalog['recipient'] != config['recipient']:
            raise RuntimeError('publication catalogue recipient mismatch')
        lib = ctypes.CDLL(config['library'])
        self.lib = lib
        budget = config['host_memory_budget']
        try:
            for name, spec in catalog['publications'].items():
                store = PreparedStore(lib, {**spec, 'byte_budget': budget})
                self.stores[name] = store
                budget -= store.metadata['bytes']
                if budget < 0:
                    raise RuntimeError('publication catalogue exceeds memory budget')
        except BaseException:
            self.close()
            raise

    def begin(self, scheduler_output):
        for rid in scheduler_output.finished_req_ids:
            self.requests.pop(rid, None)
        for req in scheduler_output.scheduled_new_reqs:
            extras = req.sampling_params.extra_args if req.sampling_params else None
            publication = (extras or {}).get('aimee_publication')
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
            if pin.store is not None:
                pin.store.activate(self.device, self.rank, self.world)
        # Bound pointer-table cache at batch boundaries. Tensor references remain
        # alive through synchronous execution; graph/asynchronous modes rejected.
        if len(self.tables) > 256:
            self.tables.clear()

    def request_ids(self, common):
        batch = self.runner.input_batch.req_ids
        indices = common.req_idx
        if indices is None:
            ids = tuple(batch[:common.num_reqs])
        else:
            ids = tuple(batch[int(i)] for i in indices[:common.num_reqs])
        if len(ids) != common.num_reqs:
            raise RuntimeError('native request/batch mapping mismatch')
        for rid in ids:
            if rid not in self.requests:
                raise RuntimeError('scheduled native request is not pinned')
        return ids

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
            banks = selected.store.activate(self.device, self.rank, self.world)
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
        catalog = json.loads(Path(config['catalog']).read_text())
        actual = hashlib.sha256((Path(config['model'])/'config.json').read_bytes()).hexdigest()
        if catalog['model_config_sha256'] != actual or catalog['recipient'] != config['recipient']:
            raise RuntimeError('replacement publication identity mismatch')
        live = {s.uid:s for s in self.stores.values()}
        live.update({p.store.uid:p.store for p in self.requests.values() if p.store is not None})
        remaining = config['host_memory_budget'] - sum(s.metadata['bytes'] for s in live.values())
        admitted = {};created=[]
        try:
            for name,spec in catalog['publications'].items():
                previous = self.stores.get(name)
                if previous is not None and all(previous.spec.get(k)==v for k,v in spec.items()):
                    admitted[name] = previous
                    continue
                if remaining <= 0: raise RuntimeError('native publication replacement exceeds pinned memory budget')
                store = PreparedStore(self.lib,{**spec,'byte_budget':remaining})
                created.append(store);remaining -= store.metadata['bytes'];admitted[name]=store
            self.stores = admitted
            self.tables.clear()
        except BaseException:
            for store in created: store.close()
            raise
        return {'publications':len(admitted),'pinned_requests':len(self.requests)}

    def close(self):
        self.tables.clear()
        for store in self.stores.values(): store.close()
        self.stores.clear()
        self.closed = True
