"""Single-command serving on the unmodified, pinned vLLM distribution."""
import argparse
import json
import os
from pathlib import Path
import sys
import math


def command(config_path):
    path = Path(config_path).resolve()
    config = json.loads(path.read_text())
    from ._model import BOUND_ADAPTER
    if BOUND_ADAPTER is not None:
        config.setdefault("library", str(Path(__file__).parent / "native/libaimee_native.so"))
    # One serving instance is one approved recipient boundary. Do not expose it
    # directly as a multi-tenant selection/authorization service.
    for key in ('model', 'library', 'catalog', 'recipient', 'host_memory_budget'):
        if key not in config:
            raise ValueError(f'missing configuration field: {key}')
    from ._model import BOUND_ADAPTER, PLUGIN_NAME
    if BOUND_ADAPTER is not None:
        if config.get("adapter", BOUND_ADAPTER) != BOUND_ADAPTER:
            raise ValueError("this plugin belongs to a different model")
        config["adapter"] = BOUND_ADAPTER
    if config.get("adapter") not in ("gemma4-12b", "gemma4-26b", "qwen3-8-27b"):
        raise ValueError("select the dedicated model plugin")
    serve = config.get('serve', {})
    if config.get('offline_prefix_capture'):
        raise ValueError('offline prefix capture cannot expose an HTTP service')
    quantization=config.get('quantization')
    if quantization is not None and (quantization!='fp8' or config.get('gguf_weights')):
        raise ValueError('supported serving quantization is fp8 without GGUF')
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
    piecewise_graphs=serve.get('enable_piecewise_graphs',False)
    hybrid=config.get('enable_hybrid_native',False)
    if type(hybrid) is not bool:raise ValueError('enable_hybrid_native must be a boolean')
    revision=config.get('model_revision')
    if hybrid and (not isinstance(revision,str) or len(revision)<40 or any(c not in '0123456789abcdef' for c in revision)):
        raise ValueError('hybrid serving requires an immutable model_revision')
    if hybrid and any((prefix_caching,async_scheduling,model_compilation,v2_runner,piecewise_graphs)):
        raise ValueError('complete hybrid native serving requires eager synchronous V1 without prefix caching')
    if hybrid and config.get('gguf_weights'):
        raise ValueError('complete hybrid prefixes currently require matching BF16 weights')
    offload=serve.get('cpu_offload_gb',0)
    pinned_offload=serve.get('cpu_offload_pinned_memory',True)
    disable_uva=serve.get('cpu_offload_disable_uva',False)
    if type(disable_uva) is not bool:raise ValueError('cpu_offload_disable_uva must be a boolean')
    if type(pinned_offload) is not bool:
        raise ValueError('cpu_offload_pinned_memory must be a boolean')
    if type(offload) not in (int,float) or not math.isfinite(offload) or offload<0:
        raise ValueError('cpu_offload_gb must be finite and nonnegative')
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
    if quantization is not None:args+=['--quantization',quantization]
    blocks=serve.get('num_gpu_blocks_override')
    if blocks is not None:
        if type(blocks) is not int or blocks<=0:raise ValueError('num_gpu_blocks_override must be positive')
        args+=['--num-gpu-blocks-override',str(blocks)]
    if offload:args+=['--cpu-offload-gb',str(offload)]
    offload_params=serve.get('cpu_offload_params')
    if offload_params is None and hybrid and offload:
        offload_params=['gate_up_proj.weight','down_proj.weight','in_proj_qkvz.weight','in_proj_ba.weight','out_proj.weight','qkv_proj.weight','o_proj.weight']
    if offload_params is not None:
        if not isinstance(offload_params,list) or not offload_params or any(not isinstance(p,str) or not p for p in offload_params):
            raise ValueError('cpu_offload_params must be nonempty parameter names')
        args+=['--cpu-offload-params',*offload_params]
    if hybrid:args+=['--mamba-ssm-cache-dtype','float32']
    gdn=serve.get('gdn_prefill_backend','triton' if hybrid else None)
    if gdn is not None:
        if gdn not in ('auto','triton','flashinfer'):raise ValueError('unsupported gdn_prefill_backend')
        args+=['--additional-config',json.dumps({'gdn_prefill_backend':gdn})]
    if model_compilation:
        # Piecewise graphs capture compiled model segments while native
        # attention remains an eager graph break with dynamic pointer tables.
        mode='PIECEWISE' if piecewise_graphs else 'NONE'
        args += ['--compilation-config',json.dumps({'mode':3,'cudagraph_mode':mode})]
    else:
        args += ['--enforce-eager']
    env = {'AIMEE_VLLM_CONFIG': str(path), 'VLLM_USE_V2_MODEL_RUNNER': '1' if v2_runner else '0',
           'VLLM_PLUGINS': PLUGIN_NAME, 'VLLM_ROCM_USE_AITER': '0', 'AIMEE_GGUF_ENABLE': '0'}
    sampler=serve.get('flashinfer_sampler')
    if sampler is not None:
        if type(sampler) is not bool:raise ValueError('flashinfer_sampler must be a boolean')
        env['VLLM_USE_FLASHINFER_SAMPLER']='1' if sampler else '0'
    if offload and not pinned_offload:
        env['VLLM_WEIGHT_OFFLOADING_DISABLE_PIN_MEMORY']='1'
        env['VLLM_WEIGHT_OFFLOADING_DISABLE_UVA']='1'
    if offload and disable_uva:env['VLLM_WEIGHT_OFFLOADING_DISABLE_UVA']='1'
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
    if len(sys.argv)>1 and sys.argv[1] in ('connect-aimee','serve'):
        from ._model import BOUND_ADAPTER
        if BOUND_ADAPTER is None:
            raise RuntimeError('use the installed model plugin command')
        from importlib.resources import files
        client=files('aimee_native_runtime').joinpath('native/aimee-model-client')
        os.environ['AIMEE_VLLM_PYTHON']=sys.executable
        os.environ['AIMEE_NATIVE_PLUGIN_CONTRACT']=str(Path(__file__).parent/'native/adapter.json')
        os.execv(str(client),[str(client),*sys.argv[1:]])
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    options = parser.parse_args()
    args, env = command(options.config)
    from ._model import BOUND_ADAPTER
    if BOUND_ADAPTER is not None:
        config = json.loads(Path(options.config).read_bytes())
        config.setdefault("adapter", BOUND_ADAPTER)
        config.setdefault("library", str(Path(__file__).parent / "native/libaimee_native.so"))
        from .model_adapter import ModelAdapter
        ModelAdapter(config)
        import tempfile
        descriptor, runtime = tempfile.mkstemp(prefix=BOUND_ADAPTER + "-", suffix=".json")
        with os.fdopen(descriptor, "w") as stream:
            json.dump(config, stream)
        import atexit
        atexit.register(lambda: Path(runtime).unlink(missing_ok=True))
        env["AIMEE_VLLM_CONFIG"] = runtime
    os.environ.update(env)
    sys.argv = args
    from vllm.entrypoints.cli.main import main as serve
    serve()

if __name__ == '__main__':
    main()
