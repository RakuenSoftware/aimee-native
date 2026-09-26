"""Private CPU preparation worker; never distribute with the serving client."""
import argparse
import json
import sys
from pathlib import Path
import torch
from transformers import AutoTokenizer, Gemma4UnifiedForConditionalGeneration
from publisher import publish


class GemmaCompiler:
    """Retain only model/tokenizer across jobs; every job gets a fresh KV cache."""
    def __init__(self, model, max_memory_tokens=1024, threads=12):
        torch.set_num_threads(threads)
        self.max_memory_tokens = max_memory_tokens
        self.tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
        self.model_path = model
        self.model = None

    def load(self):
        if self.model is None:
            self.model = Gemma4UnifiedForConditionalGeneration.from_pretrained(
                self.model_path, local_files_only=True, dtype=torch.bfloat16,
                device_map='cpu', attn_implementation='eager').eval()

    def encode(self, request):
        facts = request['response']['facts']
        records = request['identity']['records']
        if not facts or len(facts) != len(records):
            raise ValueError('incomplete selected working set')
        contents = [f['content'] for f in facts]
        if not all(isinstance(s, str) and s for s in contents):
            raise ValueError('unsupported fact content')
        if sum(len(s.encode()) for s in contents) > 1024**2:
            raise ValueError('selected content exceeds preparation budget')
        text = 'Authoritative memory:\n' + '\n'.join(contents)
        framed = self.tokenizer.apply_chat_template(
            [{'role': 'system', 'content': text}], tokenize=False,
            add_generation_prompt=False, enable_thinking=False)
        tokens = self.tokenizer.encode(framed, add_special_tokens=False)
        if not 0 < len(tokens) <= self.max_memory_tokens:
            raise ValueError('selected memory exceeds certified preparation positions')
        self.load()
        ids = torch.tensor([tokens])
        with torch.inference_mode():
            result = self.model(input_ids=ids, attention_mask=torch.ones_like(ids),
                                position_ids=torch.arange(-len(tokens), 0).unsqueeze(0),
                                use_cache=True, logits_to_keep=1)
        banks = {i: (layer.keys.detach(), layer.values.detach())
                 for i, layer in enumerate(result.past_key_values.layers)}
        return tokens, banks

    def compile(self, request, output, identity, key):
        tokens, banks = self.encode(request)
        publish(Path(output), identity, key, tokens, banks)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--identity', required=True)
    p.add_argument('--key', required=True)
    p.add_argument('--max-memory-tokens', type=int, default=1024)
    p.add_argument('--threads', type=int, default=12)
    a = p.parse_args()
    GemmaCompiler(a.model, a.max_memory_tokens, a.threads).compile(
        json.load(sys.stdin), a.output, a.identity, a.key)


if __name__ == '__main__':
    main()
