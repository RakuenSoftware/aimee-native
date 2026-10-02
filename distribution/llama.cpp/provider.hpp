#pragma once
#include "llama.h"
#include <cstdint>
#include <memory>

// Separate from the research DLPack ABI. No compiler or storage representation
// crosses this interface. The provider owns model-specific graph construction.
struct aimee_ggml_api_v1 {
    uint32_t abi;
    uint32_t struct_bytes;
    int (*open)(const char * config_path, const char * model_path, void ** session);
    llama_native_attention_callback attention;
    void (*close)(void * session);
};
using aimee_ggml_get_api_fn = const aimee_ggml_api_v1 * (*)();

class aimee_llama_provider {
public:
    aimee_llama_provider(const char * library_path, const char * config_path, const char * model_path);
    ~aimee_llama_provider();
    aimee_llama_provider(const aimee_llama_provider &) = delete;
    aimee_llama_provider & operator=(const aimee_llama_provider &) = delete;
    // Provider must outlive the llama_context and all backend operations.
    void attach(llama_context_params & params) const;
private:
    void * library_ = nullptr;
    void * session_ = nullptr;
    const aimee_ggml_api_v1 * api_ = nullptr;
};
