"""Public bootstrap for the packaged Rust Aimee connection client."""
import os
import json
from importlib.metadata import version
from pathlib import Path
import sys


def main():
    assets = Path(__file__).resolve().parent / 'native'
    binary = assets / 'aimee-native'
    library = assets / 'libaimee_native.so'
    if not binary.is_file() or not library.is_file():
        raise SystemExit('Install the complete binary Aimee plugin wheel.')
    if 'serve' in sys.argv[1:]:
        from .compatibility import check_runtime
        check_runtime()
    env = dict(os.environ, AIMEE_VLLM_PYTHON=sys.executable,
               AIMEE_NATIVE_LIBRARY=str(library))
    # Do not impose AMD transport settings on another GPU/runtime.
    env.pop('AIMEE_KERNEL_BANK', None)
    os.execve(str(binary), [str(binary), *sys.argv[1:]], env)
