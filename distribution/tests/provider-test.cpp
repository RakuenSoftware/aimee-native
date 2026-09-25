#include "provider.hpp"
#include <cassert>
#include <stdexcept>
int main(int argc, char ** argv) {
    assert(argc == 2);
    {
        aimee_llama_provider first(argv[1], "fixture", "fixture");
        aimee_llama_provider second(argv[1], "fixture", "fixture");
        llama_context_params a{}, b{}; first.attach(a); second.attach(b);
        assert(a.native_attention && b.native_attention);
        assert(a.native_attention_user_data != b.native_attention_user_data);
        assert(a.native_attention(a.native_attention_user_data, nullptr, 0, nullptr, nullptr, nullptr, nullptr, nullptr) == 1);
        assert(a.native_attention(a.native_attention_user_data, nullptr, 0, nullptr, nullptr, nullptr, nullptr, nullptr) == 2);
        assert(b.native_attention(b.native_attention_user_data, nullptr, 0, nullptr, nullptr, nullptr, nullptr, nullptr) == 1);
    }
    bool denied = false;
    try { aimee_llama_provider p(argv[1], "reject", "fixture"); }
    catch (const std::runtime_error &) { denied = true; }
    assert(denied);
    denied = false;
    try { aimee_llama_provider p("/missing/library.so", "fixture", "fixture"); }
    catch (const std::runtime_error &) { denied = true; }
    assert(denied);
}
