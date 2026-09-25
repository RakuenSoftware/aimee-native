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
            # Activation only. No model pass, tokenization, hashing or SSD read.
            banks[(s['layer'], s['value'])] = host.to(device=device).contiguous()
        self.device_banks[key] = banks
        return banks

    def close(self):
        self.device_banks.clear()
        if self.handle:
            self.lib.aimee_store_close(self.handle)
            self.handle = None

    def __del__(self):
        if getattr(self, "handle", None):
            self.close()
