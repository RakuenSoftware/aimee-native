"""Private publisher ownership glue. Storage/encoding operations remain in Rust.
Never include this module or the publisher-enabled library in client packages.
"""
import ctypes as C
import json
import os
import torch


def publish(root, model, key, tokens, banks):
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
