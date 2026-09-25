#!/usr/bin/env python3
"""Inspect final linked artifact; never treat stripping alone as secrecy."""
import pathlib
import subprocess
import sys
ALLOWED = {
    'aimee_native_abi_version', 'aimee_native_error', 'aimee_native_open',
    'aimee_native_metadata', 'aimee_native_apply', 'aimee_native_result_metadata',
    'aimee_native_result_tensor', 'aimee_native_result_free', 'aimee_native_close',
}
STORE_ALLOWED = {"aimee_admission_open", "aimee_admission_acquire", "aimee_admission_release", "aimee_admission_close", "aimee_cache_open", "aimee_cache_plan", "aimee_cache_close", "aimee_store_abi_version", "aimee_store_open", "aimee_store_metadata", "aimee_store_close"}

def audit(path, vllm=False):
    allowed = STORE_ALLOWED if vllm else ALLOWED
    symbols = subprocess.check_output(['nm', '-D', '--defined-only', str(path)], text=True)
    # Exported definitions, including unexpectedly exposed C++ bridge implementation.
    exported = {line.split()[-1].split('@')[0] for line in symbols.splitlines() if line.split()}
    unexpected = exported - allowed
    missing = allowed - exported
    if unexpected or missing:
        raise ValueError(f'ABI mismatch: unexpected={sorted(unexpected)}, missing={sorted(missing)}')
    sections = subprocess.check_output(['readelf', '-S', str(path)], text=True)
    if '.debug_' in sections or '.symtab' in sections:
        raise ValueError('private symbols/debug sections in release library')
    data = pathlib.Path(path).read_bytes()
    for marker in [b'aimee_native_publish', b'/home/virant/', b'/opt/aimee-memory-lab/', b'native layer payload mismatch']:
        if marker in data:
            raise ValueError(f'private implementation marker retained: {marker!r}')
    return {'exports': sorted(exported), 'bytes': len(data)}
if __name__ == '__main__':
    import json
    print(json.dumps(audit(sys.argv[1], "--vllm" in sys.argv[2:]), indent=2))
