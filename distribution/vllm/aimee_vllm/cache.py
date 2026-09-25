"""GPU ownership bridge; Rust owns admission, accounting and eviction decisions."""
import ctypes
import json


class DeviceCache:
    def __init__(self, lib, budget, device, rank, world):
        self.lib, self.device, self.rank, self.world = lib, device, rank, world
        lib.aimee_cache_open.argtypes = [ctypes.c_size_t]
        lib.aimee_cache_open.restype = ctypes.c_void_p
        lib.aimee_cache_plan.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lib.aimee_cache_plan.restype = ctypes.c_char_p
        lib.aimee_cache_close.argtypes = [ctypes.c_void_p]
        self.handle = lib.aimee_cache_open(budget)
        if not self.handle:
            raise RuntimeError('invalid native device memory budget')
        self.resident = {}
        self.poisoned = False
        self.stats = {'uploads': 0, 'evictions': 0, 'resident_bytes': 0, 'peak_bytes': 0}

    def ensure(self, stores, clear_tables):
        if self.poisoned:
            raise RuntimeError('native device activation failed; restart worker')
        required = {s.uid: s for s in stores}
        request = [{'id': uid, 'bytes': s.device_bytes(self.world)} for uid, s in required.items()]
        response = self.lib.aimee_cache_plan(self.handle, json.dumps(request).encode())
        if response is None:
            raise RuntimeError('pinned native memory exceeds device budget or has invalid geometry')
        plan = json.loads(response)
        try:
            if plan['evict']:
                # Tables hold tensor owners; release them before evicting banks.
                clear_tables()
            for uid in plan['evict']:
                self.resident.pop(uid).evict(self.device, self.rank, self.world)
                self.stats['evictions'] += 1
            for uid in plan['upload']:
                store = required[uid]
                store.activate(self.device, self.rank, self.world)
                self.resident[uid] = store
                self.stats['uploads'] += 1
            self.stats['resident_bytes'] = plan['resident_bytes']
            self.stats['peak_bytes'] = max(self.stats['peak_bytes'], plan['resident_bytes'])
        except BaseException:
            # The Rust plan reserves residency before DMA. A partial upload must
            # never be treated as a usable cache. Restart rather than serve it.
            self.poisoned = True
            raise

    def close(self):
        for store in self.resident.values():
            store.evict(self.device, self.rank, self.world)
        self.resident.clear()
        if self.handle:
            self.lib.aimee_cache_close(self.handle)
            self.handle = None

    def __del__(self):
        if getattr(self, 'handle', None):
            self.close()
