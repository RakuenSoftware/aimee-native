"""Single-command serving on the unmodified, pinned vLLM distribution."""
import argparse
import json
import os
from pathlib import Path
import sys


def command(config_path):
    path = Path(config_path).resolve()
    config = json.loads(path.read_text())
    # One serving instance is one approved recipient boundary. Do not expose it
    # directly as a multi-tenant selection/authorization service.
    for key in ('model', 'library', 'catalog', 'recipient', 'host_memory_budget'):
        if key not in config:
            raise ValueError(f'missing configuration field: {key}')
    serve = config.get('serve', {})
    args = ['vllm', 'serve', config['model'], '--host', serve.get('host', '127.0.0.1'),
            '--port', str(serve.get('port', 8000)), '--dtype', 'bfloat16',
            '--tensor-parallel-size', str(serve.get('tensor_parallel_size', 1)),
            '--max-model-len', str(serve.get('max_model_len', 2048)),
            '--max-num-seqs', str(serve.get('max_num_seqs', 4)),
            '--max-num-batched-tokens', str(serve.get('max_num_batched_tokens', 256)),
            '--gpu-memory-utilization', str(serve.get('gpu_memory_utilization', .75)),
            '--enforce-eager', '--no-enable-prefix-caching', '--no-async-scheduling',
            '--disable-custom-all-reduce', '--worker-cls', 'aimee_vllm.worker.AimeeWorker',
            '--attention-config', '{"backend":"CUSTOM"}',
            '--limit-mm-per-prompt', '{"image":0,"audio":0,"video":0}']
    env = {'AIMEE_VLLM_CONFIG': str(path), 'VLLM_USE_V2_MODEL_RUNNER': '0',
           'VLLM_PLUGINS': 'aimee_native', 'VLLM_ROCM_USE_AITER': '0'}
    return args, env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    options = parser.parse_args()
    args, env = command(options.config)
    os.environ.update(env)
    sys.argv = args
    from vllm.entrypoints.cli.main import main as serve
    serve()

if __name__ == '__main__':
    main()
