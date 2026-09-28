"""Private signed lab candidates. No production gate reports are fabricated."""
import argparse
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess

ROOT = Path('/opt/aimee-large-release-validation')
LAB = Path('/opt/aimee-memory-lab')
ORIGIN = Path('/opt/aimee-native-release')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-commit', required=True,
                        help='Audited source revision for the candidate, not an inherited base-image revision')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.runtime_commit):
        parser.error('--runtime-commit must be a full lowercase Git commit SHA')
    build = ROOT / 'assembly'
    identity = json.loads((ORIGIN / 'identity.json').read_text())
    digest = (build / 'image-digest.txt').read_text().strip()
    assert digest.startswith('sha256:') and len(digest) == 71
    spec = importlib.util.spec_from_file_location('private_package', build / 'package.py')
    package = importlib.util.module_from_spec(spec); spec.loader.exec_module(package)
    inputs = ROOT / 'inputs'; inputs.mkdir(exist_ok=False)
    # Extract the exact tested client library, never the private publisher library.
    container = 'aimee-larger-artifact-extract-20260928'
    subprocess.run(['podman', 'create', '--name', container,
                    'sha256:56e44a78b4ddbb228d5728311a709ee8118acc51f685b9f0e428a809b5ad2935'],
                   capture_output=True, check=True)
    try:
        subprocess.run(['podman', 'cp', container + ':/opt/aimee/libaimee_native.so',
                        str(inputs / 'libaimee_native.so')], check=True)
    finally:
        subprocess.run(['podman', 'rm', container], capture_output=True, check=True)
    shim = inputs / 'aimee-vllm'; shim.write_text('#!/bin/sh\nexec aimee-vllm "$@"\n')
    previous = json.loads((ORIGIN / 'release-plan-5.json').read_text())['files']
    common = {name: source for name, source in previous.items()
              if name.startswith('licenses/') and name != 'licenses/gemma-NOTICE.txt'}
    configs = [
        ('gemma26', 'lab-gemma4-26b-q8-native', 'gemma4-moe',
         'gemma26-release-20260928/gemma4-26b-q8.gguf', 'triton',
         'google/gemma-4-26B-A4B-it', '4d7ae4984b7db7de8f8457170b3f1a419ee76d52'),
        ('qwen27', 'lab-qwen3.8-27b-q8-native', 'model',
         'qwen27-release-20260928/qwen27-q8.gguf', 'cuda',
         'Qwen/Qwen3.8-27B', '1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0'),
    ]
    report = {'status': 'building', 'scope': 'Signed lab-only packages; production release gates remain incomplete',
              'image': identity['registry'] + '/aimee-native@' + digest, 'profiles': []}
    def save():
        (build / 'packages.json').write_text(json.dumps(report, indent=2) + '\n')
    save()
    for profile, name, source, weights, backend, model_id, revision in configs:
        model = LAB / source
        cached_revision = model / '.cache/huggingface/download/config.json.metadata'
        if cached_revision.exists():
            assert cached_revision.read_text().splitlines()[0] == revision, 'source revision mismatch'
        model_hash = hashlib.sha256((model / 'config.json').read_bytes()).hexdigest()
        native_model = profile + '-full-fp32-negative-v1-' + model_hash
        owned = inputs / profile; owned.mkdir()
        notice = owned / 'model-NOTICE.txt'
        notice.write_text(f'{model_id}\nPinned source revision: {revision}\n'
            'License metadata: Apache-2.0. Full Apache license accompanies this package.\n'
            'Modification: weights converted to Q8_0 GGUF for the Aimee native-memory runtime.\n'
            'This internal validation package does not imply endorsement by the model authors.\n')
        files = dict(common, **{'bin/aimee-vllm': str(shim), 'lib/libaimee_native.so': str(inputs / 'libaimee_native.so'),
            'models/model.gguf': str(LAB / weights), 'licenses/model-NOTICE.txt': str(notice)})
        if (model / 'LICENSE').exists():
            license_copy = owned / 'model-LICENSE.txt'; shutil.copyfile(model / 'LICENSE', license_copy)
            files['licenses/model-LICENSE.txt'] = str(license_copy)
        for path in model.iterdir():
            if path.is_file() and (path.suffix in ('.json', '.jinja', '.model') or path.name == 'merges.txt') and path.name != 'model.safetensors.index.json':
                files['models/' + path.name] = str(path)
        descriptor = {'image': report['image'], 'model_config': 'models/config.json', 'gguf_matrix_backend': backend}
        if profile == 'qwen27':
            descriptor['mm_proj'] = 'models/mmproj.gguf'
            files['models/mmproj.gguf'] = str(LAB / 'qwen27-release-20260928/qwen27-mmproj-f32.gguf')
        descriptor_path = owned / 'image.json'; descriptor_path.write_text(json.dumps(descriptor))
        files['runtime/image.json'] = str(descriptor_path)
        profile_reports = []
        for sequence in (1, 2):
            defaults = {'schema': 1, 'native_model': native_model, 'model_config_sha256': model_hash,
                        'host_memory_budget': 1024**3, 'device_memory_budget': 256*1024**2,
                        'disk_budget': 2*1024**3, 'system_memory_budget': 36*1024**3,
                        'serve': {'tensor_parallel_size': 2, 'max_model_len': 4096,
                                  'max_num_seqs': 2 if sequence == 1 else 4,
                                  'max_num_batched_tokens': 256, 'gpu_memory_utilization': .85}}
            defaults_path = owned / f'profile-{sequence}.json'; defaults_path.write_text(json.dumps(defaults))
            files['runtime/profile.json'] = str(defaults_path)
            metadata = {'schema': 1, 'sequence': sequence, 'version': f'larger-validation-{sequence}',
                'platform': 'linux-x86_64', 'model': name, 'runtime': 'vllm',
                'runtime_commit': args.runtime_commit, 'abi': 1,
                'engine': 'bin/aimee-vllm', 'library': 'lib/libaimee_native.so', 'model_file': 'models/model.gguf'}
            plan = {'manifest': metadata, 'files': dict(files)}
            (owned / f'plan-{sequence}.json').write_text(json.dumps(plan, indent=2) + '\n')
            output = ROOT / 'packages' / profile / str(sequence)
            manifest = package.package(plan, output, ORIGIN / 'private/release.key', lab_only=True)
            if sequence == 2:
                # Deduplicate only verified, immutable validation weight copies.
                # Package bytes/signatures stay identical; no source checkpoint is linked.
                first = output.parent / '1'
                old = {a['path']: a for a in json.loads((first / 'manifest.json').read_text())['artifacts']}
                for artifact in manifest['artifacts']:
                    name_ = artifact['path']
                    if name_.endswith('.gguf') and old.get(name_) == artifact:
                        target = output / name_; temporary = target.with_suffix('.link')
                        os.link(first / name_, temporary); temporary.replace(target)
            for path in [output] + list(output.rglob('*')):
                path.chmod(0o755 if path.is_dir() or path.name == 'aimee-vllm' else 0o644)
            profile_reports.append({'sequence': sequence, 'root': str(output),
                'manifest_sha256': hashlib.sha256((output / 'manifest.json').read_bytes()).hexdigest(),
                'artifact_set_sha256': package.artifact_set_digest(manifest['artifacts'])})
        report['profiles'].append({'profile': profile, 'model': name, 'native_model': native_model,
                                   'packages': profile_reports})
        save()
    report['status'] = 'built'; save()


if __name__ == '__main__':
    main()
