"""Runtime API checks, independent of GPU SKU and vendor build suffixes."""
from importlib.metadata import version
from packaging.version import Version


def check_interface():
    v = Version(version('vllm'))
    if not (Version('0.30.0') <= v < Version('0.31')):
        raise RuntimeError(f'Aimee supports the vLLM 0.30.x plugin interface; found {v}.')


def check_runtime():
    check_interface()
    import torch
    import triton
    if not torch.cuda.is_available():
        raise RuntimeError('Aimee native attention requires a GPU supported by the installed PyTorch and Triton runtime.')
    target = triton.runtime.driver.active.get_current_target()
    if target.backend not in ('cuda', 'hip'):
        raise RuntimeError(f'Unsupported Triton backend: {target.backend}; expected CUDA or HIP.')
    if not torch.cuda.is_bf16_supported():
        raise RuntimeError('This native attention implementation requires BF16 support.')
    return {'backend': target.backend, 'arch': str(target.arch),
            'torch': torch.__version__, 'triton': triton.__version__, 'vllm': version('vllm')}
