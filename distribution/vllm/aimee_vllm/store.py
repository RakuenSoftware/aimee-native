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
        admission = dict(spec)
        self.lossless_transport = admission.pop('lossless_transport', True)
        self.pipeline_transport = admission.pop('pipeline_transport', True)
        self.device_budget = admission.pop('device_budget', 256 * 1024**2)
        self.handle = self.lib.aimee_store_open(json.dumps(admission).encode())
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
        for name, args, result in (
            ('pack_prepare_transport', [ctypes.c_void_p, ctypes.c_size_t], ctypes.c_bool),
            ('pack_activate_limited', [ctypes.c_void_p, ctypes.c_int, ctypes.c_bool, ctypes.c_size_t, ctypes.c_bool], ctypes.c_void_p),
            ('pack_activate', [ctypes.c_void_p, ctypes.c_int, ctypes.c_bool], ctypes.c_void_p),
            ('activation_profile', [ctypes.c_void_p], ctypes.c_char_p),
            ('activation_free', [ctypes.c_void_p], None),
        ):
            fn = getattr(self.lib, 'aimee_store_' + name)
            fn.argtypes, fn.restype = args, result
        self.py_lib = ctypes.PyDLL(self.lib._name)
        self.py_lib.aimee_store_activation_python.argtypes = [ctypes.c_void_p]
        self.py_lib.aimee_store_activation_python.restype = ctypes.c_void_p
        self.decref = ctypes.pythonapi.Py_DecRef
        self.decref.argtypes, self.decref.restype = [ctypes.c_void_p], None

    def prepare_plan(self, rank, world):
        key = (rank, world)
        if key not in self.transfer_plans:
            handle = self.lib.aimee_store_pack_open(self.handle, rank, world)
            if not handle:
                raise RuntimeError('native head partition mismatch')
            if self.lossless_transport:
                if not self.lib.aimee_store_pack_prepare_transport(handle, self.device_budget):
                    self.lib.aimee_store_pack_close(handle)
                    raise RuntimeError('native transport admission failed')
            self.transfer_plans[key] = (handle, json.loads(self.lib.aimee_store_pack_metadata(handle)))
        return self.transfer_plans[key]

    def activate(self, device, rank, world, profile=False, staging_budget=None):
        key = (str(device), rank, world)
        if key in self.device_banks:
            return self.device_banks[key]
        handle, _ = self.prepare_plan(rank, world)
        device_index = device.index if device.index is not None else torch.cuda.current_device()
        limit = ctypes.c_size_t(-1).value if staging_budget is None else staging_budget
        result = self.lib.aimee_store_pack_activate_limited(handle, device_index, profile, limit, self.pipeline_transport)
        if not result:
            raise RuntimeError('native activation failed')
        try:
            # Rust has already read, transferred, synchronized and made every view.
            # This GIL-held call only wraps existing tensors for vLLM ownership.
            pointer = self.py_lib.aimee_store_activation_python(result)
            if not pointer:
                raise RuntimeError('native tensor wrapping failed')
            try:
                banks = ctypes.cast(pointer, ctypes.py_object).value
            finally:
                self.decref(pointer)  # Transfer the native NEW reference to Python.
            if profile:
                self.last_profile = json.loads(self.lib.aimee_store_activation_profile(result))
            self.device_banks[key] = banks
            return banks
        finally:
            self.lib.aimee_store_activation_free(result)

    def device_bytes(self, world, rank=0):
        return self.prepare_plan(rank, world)[1]['bytes']

    def staging_bytes(self, world, rank=0):
        plan = self.prepare_plan(rank, world)[1]
        return plan["transfer_bytes"] if plan.get("lossless_transport") else 0

    def reservation_bytes(self, world, rank=0):
        plan = self.prepare_plan(rank, world)[1]
        return plan.get('reservation_bytes', plan['bytes'])

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
