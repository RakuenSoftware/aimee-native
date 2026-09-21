// Vocabulary-only probe using the exact installed llama.cpp tokenizer.
#include "llama.h"
#include <iostream>
#include <string>
#include <vector>

int main(int argc, char ** argv) {
    if (argc != 2) return 2;
    auto params = llama_model_default_params();
    params.vocab_only = true;
    auto * model = llama_model_load_from_file(argv[1], params);
    if (!model) return 3;
    const auto * vocab = llama_model_get_vocab(model);
    std::string line;
    while (std::getline(std::cin, line)) {
        std::vector<llama_token> tokens(line.size() + 32);
        const int n = llama_tokenize(vocab, line.data(), line.size(),
                                    tokens.data(), tokens.size(), false, false);
        if (n < 0) { llama_model_free(model); return 4; }
        std::cout << '[';
        for (int i = 0; i < n; ++i) {
            if (i) std::cout << ',';
            std::cout << tokens[i];
        }
        std::cout << "]\n";
    }
    llama_model_free(model);
}
