"""Real Gemma 26B load and baseline inference, before native-memory validation.

Run in CT101 only after the signed lifecycle releases both GPUs.
"""
import argparse
import json
import pathlib
import subprocess
import time
import urllib.request

ROOT = pathlib.Path('/opt/aimee-memory-lab/gemma26-baseline-20260928')
IMAGE = '79d7f03eedc74943f2ffd9c1271141086ea0813bcd3f697c718e09501908cf58'
NAME = 'aimee-gemma26-baseline-20260928'
BASE = 'http://127.0.0.1:8174'
MODEL = '/opt/aimee-memory-lab/gemma4-moe'
WEIGHTS = '/opt/aimee-memory-lab/gemma26-release-20260928'
GGUF = '/weights/gemma4-26b-q8.gguf'
SERVED_MODEL = 'gemma4-26b-q8-baseline'
MMPROJ = None


def save(**data):
    (ROOT / 'status.json').write_text(json.dumps(dict(data, updated=time.time()), indent=2) + '\n')


def request(path, data=None, timeout=180):
    encoded = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(BASE + path, data=encoded,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def main(reference_bf16=False, gguf_triton=False):
    ROOT.mkdir(exist_ok=True)
    args = ['podman', 'run', '-d', '--name', NAME, '--network', 'host', '--ipc', 'host',
        '--device', '/dev/kfd', '--device', '/dev/dri/renderD128', '--device', '/dev/dri/renderD129',
        '--memory', '64g' if reference_bf16 else '36g',
        '--memory-swap', '64g' if reference_bf16 else '36g',
        '-v', MODEL + ':/model:ro',
        '-v', WEIGHTS + ':/weights:ro',
        '-e', 'VLLM_PLUGINS=aimee_native', '-e', 'AIMEE_GGUF_ENABLE=1',
        '-e', 'VLLM_USE_V2_MODEL_RUNNER=0', '-e', 'VLLM_ROCM_USE_AITER=0',
        '--entrypoint', 'vllm', IMAGE, 'serve', '/model', '--host', '127.0.0.1', '--port', BASE.rsplit(':',1)[1],
        '--served-model-name', SERVED_MODEL, '--dtype', 'bfloat16',
        '--tensor-parallel-size', '2', '--max-model-len', '4096', '--max-num-seqs', '2',
        '--max-num-batched-tokens', '256', '--gpu-memory-utilization', '.85',
        '--enforce-eager', '--no-enable-prefix-caching', '--no-async-scheduling',
        '--disable-custom-all-reduce', '--load-format', 'aimee_gguf_unified',
        '--quantization', 'gguf', '--model-loader-extra-config',
        json.dumps(dict(gguf_weights=GGUF, **({'mm_proj': MMPROJ} if MMPROJ else {}))),
        '--limit-mm-per-prompt', '{"image":0,"audio":0,"video":0}']
    if gguf_triton:
        args[args.index('--entrypoint'):args.index('--entrypoint')] = ['-e', 'VLLM_GGUF_USE_CUDA=0']
    if reference_bf16:
        for option in ['--load-format', '--quantization', '--model-loader-extra-config']:
            index = args.index(option)
            del args[index:index + 2]
        args[args.index('AIMEE_GGUF_ENABLE=1')] = 'AIMEE_GGUF_ENABLE=0'
        args[args.index('--served-model-name') + 1] = 'gemma4-26b-bf16-reference'
        args += ['--cpu-offload-gb', '8']
    (ROOT / 'command.json').write_text(json.dumps(args, indent=2) + '\n')
    save(status='starting', scope='Original BF16 checkpoint baseline with CPU offload; no memory' if reference_bf16 else 'Quantized real-model baseline; no native-memory capability claim')
    created = False
    try:
        subprocess.run(args, check=True, capture_output=True, text=True)
        created = True
        deadline = time.monotonic() + 1200
        while True:
            state = json.loads(subprocess.check_output(['podman', 'inspect', NAME], stderr=subprocess.DEVNULL))[0]['State']
            if not state['Running']:
                raise RuntimeError('baseline container exited: ' + str(state['ExitCode']))
            try:
                model = request('/v1/models', timeout=3)['data'][0]['id']
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise TimeoutError('baseline readiness exceeded 1200 seconds')
                time.sleep(5)
        save(status='probing')
        cases = [
            ('Return only the capital city of France.', 'Paris'),
            ('Compute 17 + 25. Return only the integer.', '42'),
            ('Repeat exactly this word and nothing else: Juniper', 'Juniper'),
            ('What does Python print for print(3 * 7)? Return only the output.', '21'),
        ]
        rows = []
        for prompt, expected in cases:
            started = time.perf_counter()
            result = request('/v1/chat/completions', {
                'model': model, 'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 128, 'temperature': 0, 'seed': 20260928,
                'chat_template_kwargs': {'enable_thinking': False},
            })
            answer = result['choices'][0]['message'].get('content') or ''
            rows.append({'prompt': prompt, 'expected': expected, 'answer': answer,
                'exact': answer.strip() == expected, 'response': result,
                'seconds': time.perf_counter() - started})
            (ROOT / 'responses.json').write_text(json.dumps(rows, indent=2) + '\n')
        save(status='complete', exact=sum(row['exact'] for row in rows), total=len(rows),
             image=IMAGE, scope='Four deterministic baseline smoke checks, not accuracy or native-memory certification')
    finally:
        if created:
            with (ROOT / 'server.log').open('w') as log:
                subprocess.run(['podman', 'logs', NAME], stdout=log, stderr=subprocess.STDOUT)
            subprocess.run(['podman', 'stop', '--time', '60', NAME], check=True, capture_output=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference-bf16', action='store_true')
    parser.add_argument('--gguf-triton', action='store_true', help='Use the installed GGUF plugin\'s supported Triton kernels')
    parser.add_argument('--profile', choices=['gemma26','qwen27'], default='gemma26')
    parser.add_argument('--run-suffix', default='')
    options = parser.parse_args()
    if options.reference_bf16 and options.gguf_triton:
        parser.error('GGUF kernel selection does not apply to the BF16 reference')
    if options.run_suffix and not all(c.isalnum() or c == '-' for c in options.run_suffix):
        parser.error('run suffix must be alphanumeric with optional hyphens')
    if options.profile == 'qwen27':
        if options.reference_bf16:
            parser.error('BF16 reference profile currently applies to Gemma only')
        ROOT = pathlib.Path('/opt/aimee-memory-lab/qwen27-baseline-20260928')
        NAME = 'aimee-qwen27-baseline-20260928'
        BASE = 'http://127.0.0.1:8176'
        MODEL = '/opt/aimee-memory-lab/model'
        WEIGHTS = '/opt/aimee-memory-lab/qwen27-release-20260928'
        GGUF = '/weights/qwen27-q8.gguf'
        MMPROJ = '/weights/qwen27-mmproj-f32.gguf'
        SERVED_MODEL = 'qwen3.8-27b-q8-baseline'
    if options.reference_bf16:
        ROOT = pathlib.Path('/opt/aimee-memory-lab/gemma26-bf16-reference-20260928')
        NAME = 'aimee-gemma26-bf16-reference-20260928'
        BASE = 'http://127.0.0.1:8175'
    if options.run_suffix:
        ROOT = ROOT.with_name(ROOT.name + '-' + options.run_suffix)
        NAME += '-' + options.run_suffix
    ROOT.mkdir(exist_ok=True)
    try:
        main(options.reference_bf16, options.gguf_triton)
    except BaseException as error:
        save(status='failed', error=repr(error))
        raise
