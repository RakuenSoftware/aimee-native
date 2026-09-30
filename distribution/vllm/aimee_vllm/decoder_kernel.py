"""Lossless transport decoding, compiled for the installed Triton GPU target.

This is bit unpacking, not memory encoding or a learned projection.
"""
import triton
import triton.language as tl


@triton.jit(do_not_specialize=['words', 'table0', 'table1'])
def decode_words(source, output, words, table0, table1, BLOCK: tl.constexpr):
    i = tl.program_id(0) * BLOCK + tl.arange(0, BLOCK)
    b = i * 3 // 2
    src = source.to(tl.uint64).to(tl.pointer_type(tl.uint8))
    dst = output.to(tl.uint64).to(tl.pointer_type(tl.uint16))
    lo = tl.load(src + b, i < words, 0).to(tl.uint16)
    hi = tl.load(src + b + 1, i < words, 0).to(tl.uint16)
    code = tl.where((i & 1) != 0, (lo >> 4) | (hi << 4), lo | ((hi & 15) << 8))
    symbol = code >> 8
    table = tl.where(symbol < 8, table0.to(tl.uint64), table1.to(tl.uint64))
    exponent = (table >> ((symbol & 7).to(tl.uint64) * 8)) & 255
    bits = (code & 127) | ((code & 128) << 8) | (exponent.to(tl.uint16) << 7)
    tl.store(dst + i, bits, i < words)


@triton.jit(do_not_specialize=['words', 'count'])
def decode_escapes(source, indices, output, words, count, BLOCK: tl.constexpr):
    i = tl.program_id(0) * BLOCK + tl.arange(0, BLOCK)
    src = source.to(tl.uint64).to(tl.pointer_type(tl.uint8))
    idx = indices.to(tl.uint64).to(tl.pointer_type(tl.uint32))
    dst = output.to(tl.uint64).to(tl.pointer_type(tl.uint16))
    position = tl.load(idx + i, i < count, words)
    lo = tl.load(src + 2*i, i < count, 0).to(tl.uint16)
    hi = tl.load(src + 2*i + 1, i < count, 0).to(tl.uint16)
    tl.store(dst + position, lo | (hi << 8), (i < count) & (position < words))
