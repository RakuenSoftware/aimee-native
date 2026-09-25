#!/usr/bin/env python3
"""Private release assembler. Explicit files only; signing keys stay external.

The input plan supplies Manifest fields except artifacts. `files` maps approved
client-relative paths to build outputs. `gate_evidence` maps every gate to a
private JSON report with status=passed; reports are NOT shipped. This tool does
not invent passing gate reports or produce a public release.
"""
import argparse
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import tempfile

GATES = {'native_accuracy', 'quantized_model', 'all_selected_records', 'long_conversation',
         'tenant_session_isolation', 'revision_withdrawal', 'cold_warm_latency',
         'reusable_preparation', 'clean_install', 'binary_disclosure_audit',
         'authenticated_delivery', 'license_dependency_audit'}

def allowed(path):
    if any(p in ('', '.', '..') for p in path.split('/')) or '\\' in path:
        return False
    return bool(re.fullmatch(r'runtime/(?:image|profile)\.json|bin/aimee-vllm|lib/[A-Za-z0-9_.+-]+\.so(?:\.[0-9]+)*|models/[A-Za-z0-9_.+-]+\.(?:gguf|safetensors|json|jinja|model)|licenses/[A-Za-z0-9_.+-]+\.txt', path))

def artifact_set_digest(artifacts):
    """Bind gate evidence to exact released bytes, paths and execution flags."""
    raw = json.dumps(sorted(artifacts, key=lambda a:a['path']), sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()

def package(plan, destination, signing_key, lab_only=False):
    target = pathlib.Path(destination)
    if target.exists(): raise ValueError('release destination already exists')
    metadata = dict(plan['manifest'])
    if lab_only and not metadata["model"].startswith("lab-"): raise ValueError("lab model identity required")
    reports = []
    for gate in (() if lab_only else GATES):
        evidence = json.loads(pathlib.Path(plan['gate_evidence'][gate]).read_text())
        reports.append(evidence)
        if evidence.get('status') != 'passed': raise ValueError(f'gate not passed: {gate}')
        if evidence.get('runtime_commit') != metadata['runtime_commit'] or evidence.get('model') != metadata['model']:
            raise ValueError(f'gate evidence is for a different build/model: {gate}')
    # This is the signed declaration of an internal release decision, not proof
    # that the evaluations were well designed; retain evidence privately.
    metadata['gates'] = ['lab_only'] if lab_only else sorted(GATES)
    files = plan['files']
    if not {'bin/aimee-vllm', 'lib/libaimee_native.so', metadata['model_file']} <= files.keys():
        raise ValueError('missing runtime/model artifacts')
    if 'runtime/image.json' in files:
        descriptor = json.loads(pathlib.Path(files['runtime/image.json']).read_text())
        if set(descriptor) != {'image', 'model_config'}:
            raise ValueError('invalid runtime image descriptor')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/._:-]*/[A-Za-z0-9/._:-]+@sha256:[a-fA-F0-9]{64}', descriptor['image']):
            raise ValueError('runtime image must be digest-pinned')
        if descriptor['model_config'] not in files or not re.fullmatch(r'models/[A-Za-z0-9_.+-]*config\.json',descriptor['model_config']):
            raise ValueError('missing model configuration sidecar')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.release-', dir=target.parent) as tmp:
        stage = pathlib.Path(tmp)
        artifacts = []
        for relative, source in sorted(files.items()):
            if not allowed(relative): raise ValueError(f'not a client artifact: {relative}')
            source = pathlib.Path(source)
            if source.is_symlink() or not source.is_file(): raise ValueError('source must be a regular build output')
            out = stage / relative; out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, out)
            executable = relative == 'bin/aimee-vllm'
            out.chmod(0o700 if executable else 0o600)
            with out.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            artifacts.append(dict(path=relative, bytes=out.stat().st_size, sha256=digest, executable=executable))
        identity = artifact_set_digest(artifacts)
        if any(e.get('artifact_set_sha256') != identity for e in reports):
            raise ValueError('gate evidence does not match exact release artifacts')
        metadata['artifacts'] = artifacts
        (stage/'manifest.json').write_text(json.dumps(metadata, sort_keys=True, separators=(',', ':'))+'\n')
        subprocess.run(['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(signing_key),
                        '-in', str(stage/'manifest.json'), '-out', str(stage/'manifest.sig')], check=True)
        if (stage/'manifest.sig').stat().st_size != 64: raise ValueError('Ed25519 signing key required')
        stage.rename(target)
    return metadata

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('plan'); p.add_argument('output'); p.add_argument('--signing-key', required=True); p.add_argument('--lab-only',action='store_true')
    a=p.parse_args(); package(json.loads(pathlib.Path(a.plan).read_text()), a.output, a.signing_key, lab_only=a.lab_only)
