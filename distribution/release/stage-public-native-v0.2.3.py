#!/usr/bin/env python3
"""Stage and verify signed GitHub Release assets without publishing them."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZipFile

TAG = 'native-memory-v0.2.3'
WHEEL = 'aimee_vllm-0.2.3-1-cp312-cp312-linux_x86_64.whl'
GGUF = 'vllm_gguf_plugin-0.0.5+triton-py3-none-any.whl'
BASE = f'https://github.com/RakuenSoftware/aimee/releases/download/{TAG}/'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('wheel', 'gguf', 'audit', 'live-output', 'stage', 'signing-key', 'public-key-hex'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--qwen-live-output', type=Path)
    parser.add_argument('--gemma26-live-output', type=Path)
    args = parser.parse_args()
    if args.wheel.name != WHEEL or args.gguf.name != GGUF:
        raise ValueError('unexpected public asset names')
    audit = json.loads(args.audit.read_text())
    if audit['status'] != 'passed' or audit['wheel'] != WHEEL or audit['sha256'] != sha(args.wheel):
        raise ValueError('wheel does not match its audited bytes')
    if audit.get('disclosure_hardening', {}).get('status') != 'passed':
        raise ValueError('wheel did not pass binary disclosure hardening audit')
    live = args.live_output.read_text().splitlines()
    answers = [json.loads(line) for line in live if line.startswith('{')]
    if not any('Halcyon' in result.get('answer', '') and
               'blue' in result.get('answer', '').lower() and
               result.get('usage', {}).get('prompt_tokens') == 34 and
               result.get('bank_count') == 1 for result in answers):
        raise ValueError('installed-wheel two-record live check missing')
    if 'revoked thin-client authorization withdrew native serving' not in live:
        raise ValueError('installed-wheel revocation check missing')
    qwen_validation = None
    if args.qwen_live_output:
        qwen_lines = args.qwen_live_output.read_text().splitlines()
        qwen_answers = [json.loads(line) for line in qwen_lines if line.startswith('{')]
        matches = [result for result in qwen_answers
                   if 'Halcyon' in result.get('answer', '')
                   and 'blue' in result.get('answer', '').lower()
                   and 0 < result.get('usage', {}).get('prompt_tokens', 0) < 80
                   and result.get('bank_count', 0) >= 1]
        if not matches or 'revoked thin-client authorization withdrew native serving' not in qwen_lines:
            raise ValueError('installed-wheel Qwen live/revocation check missing')
        qwen_validation = {'model': 'Qwen3.8 27B Q8 GGUF',
                           'gpu': '2 x RX 7900 XTX', 'enrolled_thinclient': True,
                           'selected_records': 2,
                           'prompt_tokens': matches[0]['usage']['prompt_tokens'],
                           'revoked_request_http_status': 503}
    gemma26_validation = None
    if args.gemma26_live_output:
        gemma26_lines = args.gemma26_live_output.read_text().splitlines()
        gemma26_answers = [json.loads(line) for line in gemma26_lines if line.startswith('{')]
        matches = [result for result in gemma26_answers
                   if 'Halcyon' in result.get('answer', '')
                   and 'blue' in result.get('answer', '').lower()
                   and 0 < result.get('usage', {}).get('prompt_tokens', 0) < 80
                   and result.get('bank_count', 0) >= 1]
        if not matches or 'revoked thin-client authorization withdrew native serving' not in gemma26_lines:
            raise ValueError('installed-wheel Gemma 26B live/revocation check missing')
        gemma26_validation = {'model': 'Gemma4 26B Q8 GGUF',
                              'gpu': '2 x RX 7900 XTX', 'enrolled_thinclient': True,
                              'selected_records': 2,
                              'prompt_tokens': matches[0]['usage']['prompt_tokens'],
                              'revoked_request_http_status': 503}
    with ZipFile(args.wheel) as archive:
        names = archive.namelist()
        metadata = archive.read(next(name for name in names if name.endswith('.dist-info/METADATA')))
        if (BASE + GGUF).encode() not in metadata or sha(args.gguf).encode() not in metadata:
            raise ValueError('GGUF dependency is not pinned to this asset')
        if any(b'192.168.' in archive.read(name) for name in names):
            raise ValueError('private-network address in public wheel')
        for marker in (b'RakuenSoftware/aimee-qwen', b'/opt/aimee-qwen',
                       b'distribution/service/', b'distribution/release/'):
            if any(marker in archive.read(name) for name in names):
                raise ValueError('private implementation/build marker in public wheel')
        if any(name.endswith(('.safetensors', '.gguf', '.pyx', '.c', '.cpp')) for name in names):
            raise ValueError('source or model weights in public wheel')
    public_key = args.public_key_hex.read_text().strip()
    if len(public_key) != 64:
        raise ValueError('unexpected Ed25519 public key')
    args.stage.mkdir(parents=True, exist_ok=False)
    for source in (args.wheel, args.gguf):
        shutil.copyfile(source, args.stage / source.name)
    manifest = {'release': TAG, 'version': '0.2.3',
        'scope': 'Self-hosted Aimee native-memory vLLM plugin preview',
        'assets': {name: {'url': BASE + name, 'sha256': sha(args.stage / name),
                         'bytes': (args.stage / name).stat().st_size}
                   for name in (WHEEL, GGUF)},
        'public_key_ed25519_hex': public_key,
        'compatibility': audit['compatibility'],
        'validated': {'installed_wheel': WHEEL, 'model': 'Gemma4 12B Q8 GGUF',
                      'gpu': 'RTX 5080', 'enrolled_thinclient': True,
                      'selected_records': 2, 'prompt_tokens': 34,
                      'revoked_request_http_status': 503,
                      'binary_disclosure_audit': True},
        'source_included': False, 'model_weights_included': False,
        'vllm_runtime_included': False}
    additional_models = [item for item in (qwen_validation, gemma26_validation) if item]
    if additional_models:
        manifest['validated']['additional_models'] = additional_models
    manifest_path = args.stage / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    sums = args.stage / 'SHA256SUMS'
    files = [args.stage / WHEEL, args.stage / GGUF, manifest_path]
    sums.write_text(''.join(f'{sha(path)}  {path.name}\n' for path in files))
    files.append(sums)
    with tempfile.TemporaryDirectory(prefix='aimee-public-stage-') as temporary:
        der = Path(temporary) / 'public.der'
        der.write_bytes(bytes.fromhex('302a300506032b6570032100' + public_key))
        for path in files:
            signature = path.with_name(path.name + '.sig')
            subprocess.run(['openssl', 'pkeyutl', '-sign', '-inkey', str(args.signing_key),
                            '-rawin', '-in', str(path), '-out', str(signature)], check=True)
            subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-keyform', 'DER',
                            '-inkey', str(der), '-rawin', '-in', str(path),
                            '-sigfile', str(signature)], check=True, capture_output=True)
    (args.stage / 'staging.json').write_text(json.dumps({
        'status': 'staged_and_signature_verified', 'published': False,
        'release': TAG, 'wheel_sha256': sha(args.stage / WHEEL),
        'manifest_sha256': sha(manifest_path), 'asset_count': len(files)}, indent=2) + '\n')
    print((args.stage / 'staging.json').read_text())


if __name__ == '__main__':
    main()
