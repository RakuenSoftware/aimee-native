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
    bank = assets / 'kernels'
    if not binary.is_file() or not library.is_file() or not (bank / 'manifest.json').is_file():
        raise SystemExit('Install the complete binary Aimee plugin wheel.')
    if 'serve' in sys.argv[1:]:
        compatibility = json.loads((assets / 'compatibility.json').read_text())
        for name in ('vllm', 'torch', 'triton'):
            actual = version(name)
            if actual != compatibility[name]:
                raise SystemExit(f'This plugin build requires {name} {compatibility[name]}; found {actual}.')
    env = dict(os.environ, AIMEE_VLLM_PYTHON=sys.executable,
               AIMEE_NATIVE_LIBRARY=str(library), AIMEE_KERNEL_BANK=str(bank))
    # The compiled gfx1100 profile uses NCCL without peer-to-peer transport.
    env.setdefault('NCCL_P2P_DISABLE', '1')
    env.setdefault('VLLM_HOST_IP', '127.0.0.1')
    os.execve(str(binary), [str(binary), *sys.argv[1:]], env)
