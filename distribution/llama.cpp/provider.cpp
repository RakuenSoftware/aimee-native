#include "provider.hpp"
#include <dlfcn.h>
#include <stdexcept>

namespace {
struct library_guard {
    void * handle;
    ~library_guard() { if (handle) dlclose(handle); }
};
}
aimee_llama_provider::aimee_llama_provider(const char * library_path, const char * config_path, const char * model_path) {
    library_guard guard{dlopen(library_path, RTLD_NOW | RTLD_LOCAL)};
    if (!guard.handle) throw std::runtime_error("native memory library unavailable");
    const auto getter = reinterpret_cast<aimee_ggml_get_api_fn>(dlsym(guard.handle, "aimee_native_ggml_get_api"));
    if (!getter) throw std::runtime_error("native library does not support this runtime");
    const auto * api = getter();
    if (!api || api->abi != 1 || api->struct_bytes != sizeof(aimee_ggml_api_v1) || !api->open || !api->attention || !api->close)
        throw std::runtime_error("native runtime interface mismatch");
    void * session = nullptr;
    int status = api->open(config_path, model_path, &session);
    if (status != 0 || !session) {
        if (session) api->close(session);
        throw std::runtime_error("native memory activation failed");
    }
    library_ = guard.handle; guard.handle = nullptr;
    api_ = api; session_ = session;
}
aimee_llama_provider::~aimee_llama_provider() {
    if (session_) api_->close(session_);
    if (library_) dlclose(library_);
}
void aimee_llama_provider::attach(llama_context_params & params) const {
    params.native_attention = api_->attention;
    params.native_attention_user_data = session_;
}
