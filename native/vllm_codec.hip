// Lossless representation decoding only; no model or learned projection.
#include <hip/hip_runtime.h>
#include <cstdint>
__global__ void decode_words(const uint8_t* input, uint16_t* output, size_t words, uint64_t table0, uint64_t table1) {
    size_t i=static_cast<size_t>(blockIdx.x)*blockDim.x+threadIdx.x;
    if (i>=words) return;
    size_t b=i*3/2;
    uint16_t code=(i&1) ? (input[b]>>4)|(uint16_t(input[b+1])<<4) : input[b]|((uint16_t(input[b+1])&15)<<8);
    unsigned symbol=code>>8;
    unsigned exponent=((symbol<8 ? table0 : table1) >> ((symbol&7)*8)) & 255;
    output[i]=(code&127)|((code&128)<<8)|(exponent<<7);
}
__global__ void decode_escapes(const uint8_t* input, const uint32_t* positions, uint16_t* output, size_t words, size_t count) {
    size_t i=static_cast<size_t>(blockIdx.x)*blockDim.x+threadIdx.x;
    if (i<count && positions[i]<words) output[positions[i]]=input[2*i]|(uint16_t(input[2*i+1])<<8);
}
extern "C" int aimee_decode_bf16(
    const void* input, const void* positions, void* output, size_t words, size_t exception_offset,
    size_t exceptions, uint64_t table0, uint64_t table1, void* stream_pointer, int device) {
    int previous=0; auto status=hipGetDevice(&previous);
    if (status!=hipSuccess) return static_cast<int>(status);
    if (previous!=device) { status=hipSetDevice(device); if (status!=hipSuccess) return static_cast<int>(status); }
    auto stream=static_cast<hipStream_t>(stream_pointer);
    hipLaunchKernelGGL(decode_words,dim3((words+255)/256),dim3(256),0,stream,
        static_cast<const uint8_t*>(input),static_cast<uint16_t*>(output),words,table0,table1);
    if (exceptions) hipLaunchKernelGGL(decode_escapes,dim3((exceptions+255)/256),dim3(256),0,stream,
        static_cast<const uint8_t*>(input)+exception_offset,static_cast<const uint32_t*>(positions),
        static_cast<uint16_t*>(output),words,exceptions);
    status=hipGetLastError();
    if (previous!=device) { auto restore=hipSetDevice(previous); if (status==hipSuccess) status=restore; }
    return static_cast<int>(status);
}
