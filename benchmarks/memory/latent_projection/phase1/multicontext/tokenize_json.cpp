#include "llama.h"
#include "json.hpp"
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

int main(int argc, char ** argv) {
    if (argc != 2) return 2;
    try {
        auto params = llama_model_default_params();
        params.vocab_only = true;
        std::unique_ptr<llama_model, decltype(&llama_model_free)> model(
            llama_model_load_from_file(argv[1], params), llama_model_free);
        if (!model) throw std::runtime_error("vocabulary load failed");
        const auto * vocab = llama_model_get_vocab(model.get());
        std::string line;
        while (std::getline(std::cin, line)) {
            const auto job = nlohmann::json::parse(line);
            std::string prompt = job.at("prompt");
            std::vector<llama_token> tokens(prompt.size()+32);
            int n = llama_tokenize(vocab, prompt.data(), prompt.size(), tokens.data(), tokens.size(),
                                   false, job.value("parse_special", false));
            if (n < 0) throw std::runtime_error("token buffer too short");
            tokens.resize(n);
            std::cout << nlohmann::json(tokens).dump() << std::endl;
        }
    } catch (const std::exception & e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
