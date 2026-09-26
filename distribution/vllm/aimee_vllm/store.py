"""Thin ownership bridge to Rust. No encoding or format reconstruction here."""
import ctypes
import json
import itertools
import torch

_identities = itertools.count()

class PreparedStore:
    def __init__(self, library, spec):
        self.uid = next(_identities)
        self.spec = dict(spec)
        self.lib = library
        self.lib.aimee_store_open.argtypes = [ctypes.c_char_p]
        self.lib.aimee_store_open.restype = ctypes.c_void_p
        self.lib.aimee_store_metadata.argtypes = [ctypes.c_void_p]
        self.lib.aimee_store_metadata.restype = ctypes.c_char_p
        self.lib.aimee_store_close.argtypes = [ctypes.c_void_p]
        self.lib.aimee_store_release_pages.argtypes = [ctypes.c_void_p]
        self.lib.aimee_store_release_pages.restype = None
        if self.lib.aimee_store_abi_version() != 1:
            raise RuntimeError("native storage ABI mismatch")
        self.handle = self.lib.aimee_store_open(json.dumps(spec).encode())
        if not self.handle:
            raise RuntimeError("native publication admission failed")
        self.metadata = json.loads(self.lib.aimee_store_metadata(self.handle))
        self.device_banks = {}
        self.transfer_plans = {}
        for name, args, result in (
            ('open', [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t], ctypes.c_void_p),
            ('metadata', [ctypes.c_void_p], ctypes.c_char_p),
            ('copy', [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t], ctypes.c_bool),
            ('close', [ctypes.c_void_p], None),
        ):
            fn = getattr(self.lib, 'aimee_store_pack_' + name)
            fn.argtypes, fn.restype = args, result

    def activate(self, device, rank, world):
        key = (str(device), rank, world)
        if key in self.device_banks:
            return self.device_banks[key]
        plan_key = (rank, world)
        if plan_key not in self.transfer_plans:
            handle = self.lib.aimee_store_pack_open(self.handle, rank, world)
            if not handle:
                raise RuntimeError('native head partition mismatch')
            self.transfer_plans[plan_key] = (handle, json.loads(self.lib.aimee_store_pack_metadata(handle)))
        handle, plan = self.transfer_plans[plan_key]
        # One bounded pinned staging allocation and one DMA, instead of a
        # synchronous allocation/copy per K/V segment. Rust owns byte layout.
        host = torch.empty(plan['bytes'] // 2, dtype=torch.bfloat16, pin_memory=True)
        if not self.lib.aimee_store_pack_copy(handle, host.data_ptr(), plan['bytes']):
            raise RuntimeError('native rank copy failed')
        packed = host.to(device=device, non_blocking=True)
        # Complete this stream before releasing source pages or staging storage.
        torch.cuda.current_stream(device).synchronize()
        banks = {}
        for seg in plan['segments']:
            shape = (seg['heads'], seg['positions'], seg['width'])
            strides = (seg['positions'] * seg['width'], seg['width'], 1)
            banks[(seg['layer'], seg['value'])] = packed.as_strided(shape, strides, seg['offset'] // 2)
        self.lib.aimee_store_release_pages(self.handle)
        self.device_banks[key] = banks
        return banks

    def device_bytes(self, world):
        # Cache TP geometry once; no disk access or content verification.
        sizes = getattr(self, '_device_sizes', None)
        if sizes is None:
            self._device_sizes = sizes = {}
        if world not in sizes:
            total = 0
            for seg in self.metadata['segments']:
                heads = seg['heads']
                if heads >= world:
                    if heads % world:
                        raise RuntimeError('native head partition mismatch')
                    local_heads = heads // world
                else:
                    if world % heads:
                        raise RuntimeError('native replicated-head partition mismatch')
                    local_heads = 1
                total += local_heads * seg['positions'] * seg['width'] * 2
            sizes[world] = total
        return sizes[world]

    def resident(self, device, rank, world):
        return self.device_banks[(str(device), rank, world)]

    def evict(self, device, rank, world):
        self.device_banks.pop((str(device), rank, world), None)

    def close(self):
        self.device_banks.clear()
        for handle, _ in getattr(self, 'transfer_plans', {}).values():
            self.lib.aimee_store_pack_close(handle)
        self.transfer_plans = {}
        if self.handle:
            self.lib.aimee_store_close(self.handle)
            self.handle = None

    def __del__(self):
        if getattr(self, "handle", None):
            self.close()
