// Isolated byte-level probe of the pinned NLTM overlay implementation.
// Opens the GGUF read-only. No model context or inference server is created.
#include "llama-ple-overlay.h"
#include "llama-mmap.h"
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>

static void check(bool ok, const char * message) {
    if (!ok) throw std::runtime_error(message);
}

int main(int argc, char ** argv) {
    if (argc != 8) return 2;
    const std::string shard = argv[1];
    const uint64_t offset = std::stoull(argv[2]), row = std::stoull(argv[3]);
    const uint64_t count = std::stoull(argv[4]), bpr = std::stoull(argv[5]);
    const uint32_t qtype = std::stoul(argv[6]);
    std::string path = std::string(argv[7]) + "/phase0-overlay-XXXXXX";
    const int fd = mkstemp(path.data());
    check(fd >= 0, "mkstemp failed");
    close(fd);
    try {
        check(row + 2 < count, "row range exceeds table");
        llama_file file(shard.c_str(), "rb");
        llama_mmap mapping(&file, 0, false, {});
        llama_mmap observer(&file, 0, false, {});
        auto * base = static_cast<unsigned char *>(mapping.addr());
        auto * other = static_cast<unsigned char *>(observer.addr());
        const size_t at = offset + row * bpr;
        std::vector<unsigned char> original(base + at, base + at + 3*bpr);
        auto write_patch = [&](unsigned char byte) {
            unsigned char header[128] = {};
            std::memcpy(header, "PLEOVLY1", 8);
            auto put = [&](int pos, uint64_t v, int n) {
                for (int i = 0; i < n; ++i) header[pos+i] = (v >> (8*i)) & 255;
            };
            put(8, 1, 2); put(12, qtype, 4); put(16, 160, 8);
            put(24, bpr, 8); put(32, 2, 8); put(40, 2, 8);
            const char * tensor = "per_layer_token_embd.weight";
            std::memcpy(header + 56, tensor, std::strlen(tensor));
            FILE * out = std::fopen(path.c_str(), "wb");
            check(out != nullptr, "open patch failed");
            check(std::fwrite(header, 1, 128, out) == 128, "write header failed");
            check(std::fwrite("{}", 1, 2, out) == 2, "write manifest failed");
            std::vector<unsigned char> payload(bpr, byte);
            for (uint64_t r = row; r < row + 2; ++r) {
                unsigned char id[8];
                for (int i = 0; i < 8; ++i) id[i] = (r >> (8*i)) & 255;
                check(std::fwrite(id, 1, 8, out) == 8, "write id failed");
                check(std::fwrite(payload.data(), 1, bpr, out) == bpr, "write row failed");
            }
            check(std::fclose(out) == 0, "close patch failed");
        };
        auto visible = [&](unsigned char byte) {
            for (size_t i = 0; i < 2*bpr; ++i) check(base[at+i] == byte, "row mismatch");
            check(std::memcmp(base + at + 2*bpr, original.data() + 2*bpr, bpr) == 0,
                  "neighbor row changed");
            check(std::memcmp(other + at, original.data(), original.size()) == 0,
                  "independent mapping changed");
        };
        write_patch(0x35);
        auto overlay = llama_ple_overlay_read_index(path.c_str());
        check(overlay.tensor_name == "per_layer_token_embd.weight" &&
              overlay.qtype == qtype && overlay.row_dim == 160 &&
              overlay.bytes_per_row == bpr, "overlay metadata mismatch");
        check(llama_ple_overlay_apply(&mapping, overlay, shard, offset, count) == 2, "apply failed");
        visible(0x35);
        const bool two_pages = overlay.mapped_pages.size() >= 2;
        // Force the change detector to check replacement even on coarse filesystems.
        write_patch(0x67);
        overlay.loaded_mtime = -1;
        check(llama_ple_overlay_reload_if_changed(&mapping, overlay, shard, offset, count) == 2,
              "replace failed");
        visible(0x67);
        check(unlink(path.c_str()) == 0, "remove failed");
        llama_ple_overlay_reload_if_changed(&mapping, overlay, shard, offset, count);
        check(std::memcmp(base + at, original.data(), original.size()) == 0, "revert failed");
        write_patch(0x23);
        check(llama_ple_overlay_reload_if_changed(&mapping, overlay, shard, offset, count) == 2,
              "reload after remove failed");
        visible(0x23);
        check(unlink(path.c_str()) == 0, "final remove failed");
        llama_ple_overlay_reload_if_changed(&mapping, overlay, shard, offset, count);
        check(std::memcmp(base + at, original.data(), original.size()) == 0, "final revert failed");
        FILE * disk = std::fopen(shard.c_str(), "rb");
        check(disk != nullptr, "reopen GGUF failed");
        check(fseeko(disk, at, SEEK_SET) == 0, "seek GGUF failed");
        std::vector<unsigned char> bytes(original.size());
        check(std::fread(bytes.data(), 1, bytes.size(), disk) == bytes.size(), "read GGUF failed");
        std::fclose(disk);
        check(bytes == original, "disk sample changed");
        std::printf("{\"apply\":true,\"replace\":true,\"remove\":true,"
                    "\"reload_after_remove\":true,\"neighbor_unchanged\":true,"
                    "\"independent_mapping_unchanged\":true,\"disk_sample_unchanged\":true,"
                    "\"crosses_page\":%s,\"row\":%llu,\"bytes_per_row\":%llu,"
                    "\"inference_tested\":false}\n", two_pages ? "true" : "false",
                    (unsigned long long) row, (unsigned long long) bpr);
    } catch (const std::exception & e) {
        unlink(path.c_str());
        std::fprintf(stderr, "%s\n", e.what());
        return 1;
    }
}
