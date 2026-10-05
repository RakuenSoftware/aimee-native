"""Private publisher ownership glue. Storage/encoding operations remain in Rust.
Never include this module or the publisher-enabled library in client packages.
"""
import ctypes as C
import json
import os
import struct
import subprocess
import torch


def publish(root, model, key, tokens, banks):
    if program := os.environ.get('AIMEE_NATIVE_PUBLISHER'):
        return publish_local(program, root, model, key, tokens, banks)
    library = C.CDLL(os.environ['AIMEE_NATIVE_LIBRARY'])
    for name, args, result in (
        ('error', [], C.c_char_p),
        ('import', [C.c_void_p], C.c_void_p),
        ('tensor_free', [C.c_void_p], None),
        ('publish', [C.c_char_p, C.POINTER(C.c_void_p), C.c_size_t], C.c_int),
    ):
        fn = getattr(library, 'aimee_native_' + name)
        fn.argtypes, fn.restype = args, result
    pointer = C.pythonapi.PyCapsule_GetPointer
    pointer.argtypes, pointer.restype = [C.py_object, C.c_char_p], C.c_void_p
    rename = C.pythonapi.PyCapsule_SetName
    rename.argtypes, rename.restype = [C.py_object, C.c_char_p], C.c_int
    layers = sorted(banks)
    owned = []
    try:
        for layer in layers:
            for tensor in banks[layer]:
                capsule = torch.utils.dlpack.to_dlpack(tensor)
                raw = pointer(capsule, b'dltensor')
                rename(capsule, b'used_dltensor')
                imported = library.aimee_native_import(raw)
                if not imported:
                    raise RuntimeError(library.aimee_native_error().decode())
                owned.append(imported)
        spec = json.dumps(dict(root=str(root), model=model, key=key,
                               tokens=tokens, layers=layers)).encode()
        pointers = (C.c_void_p * len(owned))(*owned)
        if library.aimee_native_publish(spec, pointers, len(owned)) != 0:
            raise RuntimeError(library.aimee_native_error().decode())
    finally:
        for imported in owned:
            library.aimee_native_tensor_free(imported)


def publish_local(program, root, model, key, tokens, banks):
    """Stream CPU BF16 tensors to the portable Rust writer on the inference host."""
    layers = sorted(banks)
    segments = []
    payloads = []
    for layer in layers:
        keys, values = banks[layer]
        for value, tensor in ((False, keys), (True, values)):
            if tensor.ndim != 4 or tensor.shape[0] != 1 or tensor.shape[2] != len(tokens):
                raise ValueError('incomplete local native tensor geometry')
            if tensor.dtype != torch.bfloat16:
                raise ValueError('local native tensor must be BF16')
            segments.append({'layer': layer, 'value': value,
                             'heads': tensor.shape[1], 'width': tensor.shape[3],
                             'positions': tensor.shape[2]})
            payloads.append(tensor.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes())
    header = json.dumps({'tokens': tokens, 'segments': segments}, separators=(',', ':')).encode()
    if len(header) > 1024**2:
        raise ValueError('native tensor header exceeds limit')
    child = subprocess.Popen([program, 'publish-local', '--output', str(root),
                              '--identity', model, '--key', key], stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with child.stdin:
            child.stdin.write(struct.pack('<Q', len(header)))
            child.stdin.write(header)
            for payload in payloads:
                child.stdin.write(payload)
        if child.wait(timeout=120) != 0:
            raise RuntimeError('portable native publisher failed')
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
