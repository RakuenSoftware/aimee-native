"""Private inference-host encoder entry point; bundled as a compiled extension."""
import argparse
import json
import sys
from pathlib import Path
from transformers import AutoConfig

try:
    from .gemma_compile import GemmaCompiler
    from .bounded_compile import BoundedTextCompiler
except ImportError:  # private standalone validation
    from gemma_compile import GemmaCompiler
    from bounded_compile import BoundedTextCompiler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--identity', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--max-memory-tokens', type=int, default=1024)
    parser.add_argument('--threads', type=int, default=12)
    args = parser.parse_args()
    model = Path(args.model)
    config = AutoConfig.from_pretrained(model, local_files_only=True)
    if config.model_type in ('gemma4', 'gemma4_unified'):
        index = model / 'model.safetensors.index.json'
        total = json.loads(index.read_text()).get('metadata', {}).get('total_size', 0) if index.exists() else 0
        compiler = (BoundedTextCompiler(args.model, args.max_memory_tokens, args.threads,
            compute_dtype='float32') if total > 30 * 1024**3 else
            GemmaCompiler(args.model, args.max_memory_tokens, args.threads))
    elif config.model_type == 'qwen3_5':
        compiler = BoundedTextCompiler(args.model, args.max_memory_tokens, args.threads,
            compute_dtype='float32')
    else:
        raise ValueError('local native encoder has no certified implementation for this model')
    try:
        compiler.compile(json.load(sys.stdin), args.output, args.identity, args.key)
    finally:
        if hasattr(compiler, 'close'):
            compiler.close()


if __name__ == '__main__':
    main()
