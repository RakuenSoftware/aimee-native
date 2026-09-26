"""Private tensor-owner bridge. Rust decides scope and valid prefix reuse."""
import ctypes
import json

class ReusePlanner:
    def __init__(self, library, limit):
        self.lib = ctypes.CDLL(library)
        self.lib.aimee_reuse_open.argtypes = [ctypes.c_size_t]
        self.lib.aimee_reuse_open.restype = ctypes.c_void_p
        self.lib.aimee_reuse_plan.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_bool]
        self.lib.aimee_reuse_plan.restype = ctypes.c_char_p
        self.lib.aimee_reuse_close.argtypes = [ctypes.c_void_p]
        self.handle = self.lib.aimee_reuse_open(limit)
        if not self.handle:
            raise ValueError('invalid reuse capacity')

    def plan(self, identity, tokens, commit=False):
        response = self.lib.aimee_reuse_plan(self.handle, json.dumps({'identity': identity, 'tokens': tokens}).encode(), commit)
        if not response:
            raise ValueError('invalid preparation reuse identity')
        return json.loads(response)

    def close(self):
        if self.handle:
            self.lib.aimee_reuse_close(self.handle)
            self.handle = None

    def __del__(self):
        if getattr(self, 'handle', None):
            self.close()
