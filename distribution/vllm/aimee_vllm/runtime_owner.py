"""Thin CPython adapter for the opaque Rust-owned vLLM runtime state."""
import ctypes
import json


class RuntimeOwner:
    def __init__(self, library, config):
        self.lib = library
        library.aimee_vllm_runtime_open.argtypes = [ctypes.c_char_p]
        library.aimee_vllm_runtime_open.restype = ctypes.c_void_p
        library.aimee_vllm_runtime_snapshot.argtypes = [ctypes.c_void_p]
        library.aimee_vllm_runtime_snapshot.restype = ctypes.c_char_p
        library.aimee_vllm_runtime_begin.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        library.aimee_vllm_runtime_begin.restype = ctypes.c_char_p
        library.aimee_vllm_runtime_refresh.argtypes = [ctypes.c_void_p]
        library.aimee_vllm_runtime_refresh.restype = ctypes.c_char_p
        library.aimee_vllm_attention_plan.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        library.aimee_vllm_attention_plan.restype = ctypes.c_char_p
        library.aimee_vllm_runtime_close.argtypes = [ctypes.c_void_p]
        payload = {k: config[k] for k in ('catalog', 'model', 'recipient')}
        self.handle = library.aimee_vllm_runtime_open(json.dumps(payload, separators=(',', ':')).encode())
        if not self.handle:
            raise RuntimeError('native vLLM runtime initialization failed')

    def _decode(self, raw):
        if not raw:
            raise RuntimeError('native vLLM runtime operation failed')
        return json.loads(raw)

    def snapshot(self):
        return self._decode(self.lib.aimee_vllm_runtime_snapshot(self.handle))

    def begin(self, finished, new_requests):
        return self._decode(self.lib.aimee_vllm_runtime_begin(
            self.handle,
            json.dumps(list(finished), separators=(',', ':')).encode(),
            json.dumps(new_requests, separators=(',', ':')).encode(),
        ))

    def refresh(self):
        return self._decode(self.lib.aimee_vllm_runtime_refresh(self.handle))

    def attention_plan(self, request):
        return self._decode(self.lib.aimee_vllm_attention_plan(
            self.handle, json.dumps(request, separators=(',', ':')).encode()))

    def close(self):
        if getattr(self, 'handle', None):
            self.lib.aimee_vllm_runtime_close(self.handle)
            self.handle = None

    def __del__(self):
        if getattr(self, 'handle', None):
            self.close()
