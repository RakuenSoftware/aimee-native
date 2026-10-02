"""Thin vLLM/Torch adapter. Rust owns catalogue identity and request pin semantics."""
from dataclasses import dataclass
import ctypes
import torch
from .store import PreparedStore
from .cache import DeviceCache
from .runtime_owner import RuntimeOwner

CURRENT = None


@dataclass(frozen=True)
class Pin:
    publication: str | None
    key: str | None
    store: object = None


class State:
    def __init__(self, config, runner, device, rank, world):
        self.runner, self.device, self.rank, self.world = runner, device, rank, world
        self.requests = {}
        self.stores = {}
        self.store_by_key = {}
        self.publication_keys = {}
        self.tables = {}
        self.closed = False
        self.config = config
        lib = ctypes.CDLL(config['library'])
        self.lib = lib
        self.owner = RuntimeOwner(lib, config)
        lib.aimee_store_runtime_warmup.argtypes = [ctypes.c_int]
        lib.aimee_store_runtime_warmup.restype = ctypes.c_bool
        if not lib.aimee_store_runtime_warmup(device.index):
            raise RuntimeError('native runtime warmup failed')
        self.cache = DeviceCache(lib, config.get("device_memory_budget", 256 * 1024**2), device, rank, world)
        try:
            snapshot = self.owner.snapshot()
            self._admit_publications(snapshot)
            self._sync_pins(snapshot)
        except BaseException:
            self.close()
            raise

    def _store_spec(self, spec, budget):
        return {
            **spec,
            'byte_budget': budget,
            'disk_backed': self.config.get('disk_backed', False),
            'lossless_transport': self.config.get('lossless_transport', True),
            'pipeline_transport': self.config.get('pipeline_transport', True),
            'device_budget': self.config.get('device_memory_budget', 256 * 1024**2),
        }

    def _admit_publications(self, snapshot):
        disk_backed = self.config.get('disk_backed', False)
        used = 0 if disk_backed else sum(s.metadata['bytes'] for s in self.store_by_key.values())
        remaining = self.config['host_memory_budget'] - used
        if remaining < 0:
            raise RuntimeError('publication catalogue exceeds memory budget')
        current = {}
        keys = {}
        created = []
        try:
            for publication in snapshot['publications']:
                name, key, spec = publication['name'], publication['key'], publication['spec']
                store = self.store_by_key.get(key)
                if store is None:
                    if remaining <= 0:
                        raise RuntimeError('native publication replacement exceeds pinned memory budget')
                    store = PreparedStore(self.lib, self._store_spec(spec, remaining))
                    store.prepare_plan(self.rank, self.world)
                    self.store_by_key[key] = store
                    created.append((key, store))
                    if not disk_backed:
                        remaining -= store.metadata['bytes']
                current[name] = store
                keys[name] = key
            self.stores = current
            self.publication_keys = keys
            self.catalog_digest = snapshot['catalog_digest']
        except BaseException:
            for key, store in created:
                self.store_by_key.pop(key, None)
                store.close()
            raise

    def _sync_pins(self, snapshot):
        requests = {}
        for row in snapshot['pins']:
            key = row['key']
            store = None if key is None else self.store_by_key.get(key)
            if key is not None and store is None:
                raise RuntimeError('Rust pinned a publication revision without an admitted store')
            requests[row['id']] = Pin(row['publication'], key, store)
        self.requests = requests

    def _collect_stale(self):
        keep = set(self.publication_keys.values())
        keep.update(pin.key for pin in self.requests.values() if pin.key is not None)
        resident = set(id(store) for store in self.cache.resident.values())
        for key, store in list(self.store_by_key.items()):
            if key not in keep and id(store) not in resident:
                store.close()
                del self.store_by_key[key]

    def begin(self, scheduler_output):
        new = []
        for req in scheduler_output.scheduled_new_reqs:
            extras = req.sampling_params.extra_args if req.sampling_params else None
            new.append({
                'id': req.req_id,
                'publication': (extras or {}).get('aimee_publication'),
                'catalog_digest': (extras or {}).get('aimee_catalog_digest'),
            })
        if scheduler_output.finished_req_ids or new:
            snapshot = self.owner.begin(scheduler_output.finished_req_ids, new)
            self._sync_pins(snapshot)
            self.cache.ensure((p.store for p in self.requests.values() if p.store is not None), self.tables.clear)
            self._collect_stale()
        if len(self.tables) > 256:
            self.tables.clear()

    def request_ids(self, common):
        indices = common.req_idx
        if hasattr(self.runner, 'req_states'):
            if indices is None:
                raise RuntimeError('native V2 attention is missing request slots')
            slots = {index: rid for rid, index in self.runner.req_states.req_id_to_index.items()}
            ids = tuple(slots.get(int(i)) for i in indices[:common.num_reqs])
        else:
            batch = self.runner.input_batch.req_ids
            ids = tuple(batch[:common.num_reqs]) if indices is None else tuple(
                batch[int(i)] for i in indices[:common.num_reqs])
        if len(ids) != common.num_reqs or len(set(ids)) != len(ids):
            raise RuntimeError('native request/batch mapping mismatch')
        for rid in ids:
            if rid not in self.requests:
                raise RuntimeError('scheduled native request is not pinned')
        return ids

    def upstream_only_without_slots(self, common):
        return (common.req_idx is None and bool(self.requests)
                and all(pin.store is None for pin in self.requests.values()))

    def memory_table(self, ids, layer, dtype, heads, width):
        selections = tuple(self.requests[r] for r in ids)
        if not any(s.store is not None for s in selections):
            return None
        cache_key = (tuple(s.key for s in selections), layer, dtype, heads, width)
        if cache_key in self.tables:
            return self.tables[cache_key]
        keys, values, lengths, owners = [], [], [], []
        for selected in selections:
            if selected.store is None:
                keys.append(0); values.append(0); lengths.append(0)
                continue
            banks = selected.store.resident(self.device, self.rank, self.world)
            k, v = banks[(layer, False)], banks[(layer, True)]
            if k.shape != v.shape or k.shape[0] != heads or k.shape[2] != width or k.dtype != dtype:
                raise RuntimeError('native attention bank geometry/dtype mismatch')
            keys.append(k.data_ptr()); values.append(v.data_ptr()); lengths.append(k.shape[1])
            owners.extend((k, v))
        tables = tuple(torch.tensor(a, dtype=t, device=self.device) for a, t in
                       [(keys, torch.uint64), (values, torch.uint64), (lengths, torch.int32)])
        result = (*tables, owners)
        self.tables[cache_key] = result
        return result

    def refresh(self):
        """Rust validates and advances the catalogue; Python only admits matching tensor stores."""
        snapshot = self.owner.refresh()
        self._admit_publications(snapshot)
        self._sync_pins(snapshot)
        self.tables.clear()
        if not self.requests:
            self.cache.close()
            self.cache = DeviceCache(
                self.lib, self.config.get("device_memory_budget", 256 * 1024**2),
                self.device, self.rank, self.world)
        self._collect_stale()
        return {
            'publications': len(self.stores),
            'pinned_requests': len(self.requests),
            'catalog_digest': self.catalog_digest,
        }

    def close(self):
        self.tables.clear()
        if hasattr(self, "cache"):
            self.cache.close()
        self.requests.clear()
        for store in set(self.store_by_key.values()):
            store.close()
        self.store_by_key.clear()
        self.stores.clear()
        if hasattr(self, 'owner'):
            self.owner.close()
        self.closed = True
