// Isolated, serial PLE trials. The installed runtime and GGUF stay unchanged.
#include "llama.h"
#include "ggml-backend.h"
#include "json.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <vector>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

using json = nlohmann::ordered_json;
using Clock = std::chrono::steady_clock;
extern const std::vector<std::pair<std::string, ggml_tensor *>> &
    llama_internal_get_tensor_map(const llama_model * model);

static void require(bool value, const char * message) {
    if (!value) throw std::runtime_error(message);
}
static double seconds(Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now() - start).count();
}
static std::string piece(const llama_vocab * vocab, llama_token token) {
    std::vector<char> buf(512);
    int n = llama_token_to_piece(vocab, token, buf.data(), buf.size(), 0, true);
    require(n >= 0, "token piece exceeded buffer");
    return std::string(buf.data(), n);
}

struct PrivateRows {
    ggml_tensor * table;
    uint64_t offset;
    int fd;
    size_t page = sysconf(_SC_PAGESIZE);
    std::map<uintptr_t, uint64_t> pages;
    std::map<int64_t, std::vector<unsigned char>> originals;
    PrivateRows(ggml_tensor * t, const std::string & shard, uint64_t off): table(t), offset(off) {
        require(t && t->type == GGML_TYPE_IQ4_NL && t->ne[0] == 160, "unexpected table");
        require(ggml_backend_buffer_is_host(t->buffer), "PLE table must stay on host");
        require(ggml_row_size(t->type, 160) == 90, "unexpected row size");
        require(uintptr_t(t->data) % page == off % page, "table mapping alignment mismatch");
        fd = open(shard.c_str(), O_RDONLY);
        require(fd >= 0, "cannot open read-only GGUF");
    }
    void restore() {
        for (auto [addr, file_offset] : pages) {
            require(mmap(reinterpret_cast<void *>(addr), page, PROT_READ,
                         MAP_PRIVATE | MAP_FIXED, fd, file_offset) != MAP_FAILED, "restore mmap failed");
        }
        for (const auto & [id, raw] : originals) {
            auto * ptr = static_cast<unsigned char *>(table->data) + id * 90;
            require(std::memcmp(ptr, raw.data(), 90) == 0, "restored row differs");
        }
        pages.clear();
        originals.clear();
    }
    ~PrivateRows() { close(fd); }
    json apply(const std::string & path) {
        std::ifstream file(path);
        json doc; file >> doc;
        require(doc.at("rows").size() == 8, "single-fact probe requires eight rows");
        struct Row { int64_t id; std::vector<unsigned char> bytes; };
        std::vector<Row> pending;
        double error = 0, magnitude = 0;
        std::set<int64_t> seen;
        for (const auto & r : doc.at("rows")) {
            int64_t id = r.at("id");
            require(id >= 160000374 && id < 320001536 && id < table->ne[1], "not a trigram row");
            require(seen.insert(id).second, "duplicate overlay row");
            auto values = r.at("values").get<std::vector<float>>();
            require(values.size() == 160, "invalid row dimension");
            for (float v : values) require(std::isfinite(v), "nonfinite input row");
            std::vector<unsigned char> encoded(90);
            require(ggml_quantize_chunk(table->type, values.data(), encoded.data(), 0, 1, 160, nullptr) == 90,
                    "quantization size mismatch");
            float decoded[160];
            ggml_get_type_traits(table->type)->to_float(encoded.data(), decoded, 160);
            for (int i = 0; i < 160; ++i) {
                require(std::isfinite(decoded[i]), "nonfinite encoded row");
                error += std::pow(double(values[i])-decoded[i], 2);
                magnitude += double(values[i])*values[i];
            }
            pending.push_back({id, std::move(encoded)});
        }
        // Validate every original row before changing any mapping.
        for (const auto & r : pending) {
            std::vector<unsigned char> raw(90);
            require(pread(fd, raw.data(), 90, offset + r.id*90) == 90, "short model read");
            auto * ptr = static_cast<unsigned char *>(table->data) + r.id*90;
            require(std::memcmp(ptr, raw.data(), 90) == 0, "model mapping differs from disk");
            originals.emplace(r.id, raw);
        }
        for (const auto & r : pending) {
            const uintptr_t at = uintptr_t(table->data) + r.id*90;
            const uint64_t file_at = offset + r.id*90;
            for (uintptr_t addr = at/page*page; addr < at+90; addr += page) {
                if (pages.count(addr)) continue;
                uint64_t file_offset = file_at - (at - at/page*page) + (addr - at/page*page);
                require(mmap(reinterpret_cast<void *>(addr), page, PROT_READ | PROT_WRITE,
                             MAP_PRIVATE | MAP_FIXED, fd, file_offset) != MAP_FAILED, "overlay mmap failed");
                pages.emplace(addr, file_offset);
            }
            std::memcpy(reinterpret_cast<void *>(at), r.bytes.data(), 90);
        }
        return json{{"rows", seen}, {"payload_bytes", 720},
                    {"relative_quantization_l2", std::sqrt(error/std::max(magnitude,1e-30))}};
    }
};

int main(int argc, char ** argv) {
    if (argc != 5) {
        std::cerr << "runner MODEL_FIRST_SHARD TABLE_SHARD TABLE_OFFSET GPU_LAYERS\n";
        return 2;
    }
    try {
        ggml_backend_load_all();
        llama_backend_init();
        auto mp = llama_model_default_params();
        mp.n_gpu_layers = std::stoi(argv[4]);
        mp.load_mode = LLAMA_LOAD_MODE_MMAP;
        mp.lazy_mode = LLAMA_LAZY_MODE_ON;
        const auto start = Clock::now();
        std::unique_ptr<llama_model, decltype(&llama_model_free)> model(
            llama_model_load_from_file(argv[1], mp), llama_model_free);
        require(bool(model), "model load failed");
        ggml_tensor * table = nullptr;
        for (const auto & [name, t] : llama_internal_get_tensor_map(model.get()))
            if (name == "per_layer_token_embd.weight") table = t;
        PrivateRows overlay(table, argv[2], std::stoull(argv[3]));
        const auto * vocab = llama_model_get_vocab(model.get());
        const int nv = llama_vocab_n_tokens(vocab);
        std::cout << json{{"event","ready"},{"load_seconds",seconds(start)},
                          {"table_buffer",ggml_backend_buffer_name(table->buffer)}}.dump() << std::endl;
        std::string line;
        while (std::getline(std::cin, line)) {
            const auto job = json::parse(line);
            if (job.value("quit", false)) break;
            const auto t0 = Clock::now();
            json result{{"id",job.at("id")}};
            overlay.restore();
            if (job.contains("overlay")) result["overlay"] = overlay.apply(job.at("overlay"));
            std::string prompt = job.at("prompt");
            std::vector<llama_token> tokens(prompt.size() + 32);
            const int n = llama_tokenize(vocab, prompt.data(), prompt.size(), tokens.data(), tokens.size(), false, false);
            require(n > 0 && n < 512, "invalid prompt size");
            tokens.resize(n);
            result["prompt_tokens"] = tokens;
            auto cp = llama_context_default_params();
            cp.n_ctx = 512; cp.n_batch = 512; cp.n_ubatch = 512;
            cp.n_threads = 8; cp.n_threads_batch = 8;
            cp.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_DISABLED;
            cp.type_k = GGML_TYPE_F32; cp.type_v = GGML_TYPE_F32;
            std::unique_ptr<llama_context, decltype(&llama_free)> ctx(
                llama_init_from_model(model.get(), cp), llama_free);
            require(bool(ctx), "context creation failed");
            const auto prefill = Clock::now();
            require(llama_decode(ctx.get(), llama_batch_get_one(tokens.data(), tokens.size())) == 0, "prefill failed");
            result["prefill_seconds"] = seconds(prefill);
            float * logits = llama_get_logits_ith(ctx.get(), -1);
            const int target = job.at("target");
            require(target >= 0 && target < nv, "target out of range");
            float max = *std::max_element(logits, logits + nv);
            require(std::isfinite(max), "nonfinite logits");
            double sum = 0;
            int rank = 1;
            for (int i = 0; i < nv; ++i) {
                require(std::isfinite(logits[i]), "nonfinite logits");
                sum += std::exp(double(logits[i])-max);
                if (logits[i] > logits[target]) ++rank;
            }
            result["target_probability"] = std::exp(double(logits[target])-max)/sum;
            result["target_rank"] = rank;
            if (job.contains("logits_file")) {
                std::ofstream out(job.at("logits_file").get<std::string>(), std::ios::binary);
                out.write(reinterpret_cast<char *>(logits), nv*sizeof(float));
                require(bool(out), "logits write failed");
            }
            std::vector<int> generated;
            std::string text;
            const int cap = job.value("generate", 1);
            require(cap >= 1 && cap <= 32, "generation cap out of range");
            for (int i = 0; i < cap; ++i) {
                llama_token token = std::max_element(logits, logits + nv) - logits;
                generated.push_back(token);
                text += piece(vocab, token);
                if (llama_vocab_is_eog(vocab, token) || i+1 == cap) break;
                require(llama_decode(ctx.get(), llama_batch_get_one(&token, 1)) == 0, "decode failed");
                logits = llama_get_logits_ith(ctx.get(), -1);
            }
            ctx.reset();
            overlay.restore();
            result["generated_tokens"] = generated;
            result["generated_text"] = text;
            result["fresh_context"] = true;
            result["rows_restored"] = true;
            result["elapsed_seconds"] = seconds(t0);
            std::cout << result.dump() << std::endl;
        }
    } catch (const std::exception & e) {
        std::cerr << "FAILED: " << e.what() << '\n';
        return 1;
    }
}
