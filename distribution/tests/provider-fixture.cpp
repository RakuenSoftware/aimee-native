// Interface-only test fixture. Does not encode memory or implement a model.
#include "provider.hpp"
#include <cstring>
static int open_session(const char * config, const char *, void ** session) {
    if (std::strcmp(config, "reject") == 0) return -1;
    *session = new int(0); return 0;
}
static int attention(void * state, ggml_context *, int32_t, ggml_tensor **, ggml_tensor **, ggml_tensor **, ggml_tensor **, int64_t *) {
    return ++*static_cast<int *>(state);
}
static void close_session(void * state) { delete static_cast<int *>(state); }
extern "C" const aimee_ggml_api_v1 * aimee_native_ggml_get_api() {
    static const aimee_ggml_api_v1 api{1, sizeof(aimee_ggml_api_v1), open_session, attention, close_session};
    return &api;
}
