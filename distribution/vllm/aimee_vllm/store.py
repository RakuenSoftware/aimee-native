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

    def activate(self, device, rank, world):
        key = (str(device), rank, world)
        if key in self.device_banks:
            return self.device_banks[key]
        banks = {}
        for s in self.metadata['segments']:
            buffer = (ctypes.c_ubyte * s['bytes']).from_address(s['pointer'])
            host = torch.frombuffer(buffer, dtype=torch.bfloat16).reshape(s['heads'], s['positions'], s['width'])
            if s['heads'] >= world:
                if s['heads'] % world:
                    raise RuntimeError('native head partition mismatch')
                host = host.chunk(world, dim=0)[rank]
            else:
                if world % s['heads']:
                    raise RuntimeError('native replicated-head partition mismatch')
                head = rank // (world // s['heads'])
                host = host[head:head+1]
            # Activation only. Disk-backed pages can fault here, before attention;
            # no model pass, tokenization, hashing or file reopen.
            banks[(s['layer'], s['value'])] = host.to(device=device).contiguous()
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
        if self.handle:
            self.lib.aimee_store_close(self.handle)
            self.handle = None

    def __del__(self):
        if getattr(self, "handle", None):
            self.close()
