#include "ggml.h"
#include <cstdint>

extern "C" int phase1_dequant(int type, const void * raw, float * out, int64_t count) {
    if (type < 0 || type >= GGML_TYPE_COUNT || count <= 0) return 1;
    const auto * traits = ggml_get_type_traits(static_cast<ggml_type>(type));
    if (!traits || !traits->to_float || count % ggml_blck_size(static_cast<ggml_type>(type))) return 2;
    traits->to_float(raw, out, count);
    return 0;
}

extern "C" int phase1_encode_iq4_row(const float * values, void * out) {
    return ggml_quantize_chunk(GGML_TYPE_IQ4_NL, values, out, 0, 1, 160, nullptr) == 90 ? 0 : 1;
}
