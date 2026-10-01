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
    prefix_caching=serve.get('enable_prefix_caching',False)
    if type(prefix_caching) is not bool:
        raise ValueError('enable_prefix_caching must be a boolean')
    async_scheduling=serve.get('async_scheduling',False)
    if type(async_scheduling) is not bool:
        raise ValueError('async_scheduling must be a boolean')
    model_compilation=serve.get('enable_model_compilation',False)
    if type(model_compilation) is not bool:
        raise ValueError('enable_model_compilation must be a boolean')
    v2_runner=serve.get('v2_model_runner',False)
    if type(v2_runner) is not bool:
        raise ValueError('v2_model_runner must be a boolean')
    if v2_runner:
        raise ValueError('v2_model_runner is not supported: request identities are unavailable during attention')
    piecewise_graphs=serve.get('enable_piecewise_graphs',False)
    if type(piecewise_graphs) is not bool:
        raise ValueError('enable_piecewise_graphs must be a boolean')
    if piecewise_graphs and not model_compilation:
        raise ValueError('piecewise graphs require model compilation')
    args = ['vllm', 'serve', config['model'], '--host', serve.get('host', '127.0.0.1'),
            '--port', str(serve.get('port', 8000)), '--dtype', 'bfloat16',
            '--tensor-parallel-size', str(serve.get('tensor_parallel_size', 1)),
            '--max-model-len', str(serve.get('max_model_len', 2048)),
            '--max-num-seqs', str(serve.get('max_num_seqs', 4)),
            '--max-num-batched-tokens', str(serve.get('max_num_batched_tokens', 256)),
            '--gpu-memory-utilization', str(serve.get('gpu_memory_utilization', .75)),
            '--middleware', 'aimee_vllm.admission.NativeAdmission',
            '--enable-prefix-caching' if prefix_caching else '--no-enable-prefix-caching',
            '--async-scheduling' if async_scheduling else '--no-async-scheduling',
            '--disable-custom-all-reduce', '--worker-cls', 'aimee_vllm.worker.AimeeWorker',
            '--attention-config', '{"backend":"CUSTOM"}',
            '--limit-mm-per-prompt', '{"image":0,"audio":0,"video":0}']
    if model_compilation:
        # Piecewise graphs capture compiled model segments while native
        # attention remains an eager graph break with dynamic pointer tables.
        mode='PIECEWISE' if piecewise_graphs else 'NONE'
        args += ['--compilation-config',json.dumps({'mode':3,'cudagraph_mode':mode})]
    else:
        args += ['--enforce-eager']
    env = {'AIMEE_VLLM_CONFIG': str(path), 'VLLM_USE_V2_MODEL_RUNNER': '0',
           'VLLM_PLUGINS': 'aimee_native', 'VLLM_ROCM_USE_AITER': '0', 'AIMEE_GGUF_ENABLE': '0'}
    if config.get('gguf_weights'):
        loader = {'gguf_weights': config['gguf_weights']}
        if config.get('mm_proj'):
            loader['mm_proj'] = config['mm_proj']
        backend = config.get('gguf_matrix_backend')
        if backend is None:
            backend = 'triton'
        if backend not in ('cuda', 'triton'):
            raise ValueError('unsupported GGUF matrix backend')
        env['VLLM_GGUF_USE_CUDA'] = '0' if backend == 'triton' else '1'
        args += ['--model-loader-extra-config', json.dumps(loader), '--load-format',
                 'aimee_gguf_unified', '--quantization', 'gguf']
        env['AIMEE_GGUF_ENABLE']='1'
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
