"""Public framework operations only. Rust owns data, planning and activation.

No ATen ABI, HIP linkage, custom allocation, or Python storage implementation.
These wrappers run on activation; resident attention does not call them.
"""
import torch


def host(size):
    return torch.empty(size // 2, dtype=torch.bfloat16, pin_memory=True)


def device(size, ordinal):
    return torch.empty(size // 2, dtype=torch.bfloat16, device=f'cuda:{ordinal}')


def stream(tensor):
    return torch.cuda.current_stream(tensor.device).cuda_stream


def upload(tensor, ordinal):
    return tensor.to(device=f'cuda:{ordinal}', non_blocking=True)


def upload_range(source, target, offset, size):
    target.narrow(0, offset // 2, size // 2).copy_(source.narrow(0, offset // 2, size // 2), non_blocking=True)


def wait(tensor):
    torch.cuda.current_stream(tensor.device).synchronize()


def decode(source, indices, output, words, exception_offset, exceptions, table0, table1, stream, ordinal):
    from .decoder_kernel import decode_words, decode_escapes
    import triton
    # Rust retains all allocations through completion. Explicit stream selection
    # keeps upload, decoding and synchronization ordered on both HIP and CUDA.
    with torch.cuda.device(ordinal), torch.cuda.stream(torch.cuda.ExternalStream(stream, device=ordinal)):
        decode_words[(triton.cdiv(words, 256),)](source, output, words, table0, table1, BLOCK=256)
        if exceptions:
            decode_escapes[(triton.cdiv(exceptions, 256),)](source + exception_offset, indices, output, words, exceptions, BLOCK=256)
