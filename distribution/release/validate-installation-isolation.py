#!/usr/bin/env python3
"""Check co-installation and independent uninstall in the owned validation rig."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/opt/aimee-native-serving')
OUT = ROOT / 'model-plugins-shared-r10/installation-isolation'
BASE = ROOT / 'clean-release-env-build2'
ENVIRONMENT = ROOT / 'model-plugin-isolation-env-r10'


def main():
    OUT.mkdir(mode=0o700)
    subprocess.run([BASE / 'bin/python', '-m', 'venv', ENVIRONMENT], check=True)
    site = ENVIRONMENT / 'lib/python3.12/site-packages'
    dependencies = BASE / 'lib/python3.12/site-packages'
    for origin in dependencies.iterdir():
        if origin.name.startswith(('aimee_', 'aimee-')) or origin.name == '__pycache__' or (site / origin.name).exists():
            continue
        (site / origin.name).symlink_to(origin, target_is_directory=origin.is_dir())
    env = dict(os.environ, PYTHONNOUSERSITE='1')
    for name in ('PYTHONPATH', 'PYTHONHOME', 'AIMEE_NATIVE_PLUGIN_CONTRACT', 'VLLM_PLUGINS', 'AIMEE_VLLM_CONFIG'):
        env.pop(name, None)
    python = ENVIRONMENT / 'bin/python'
    wheels = ROOT / 'model-plugins-shared-r10/release-with-notices'
    subprocess.run([python, '-m', 'pip', 'install', '--no-index', '--find-links', wheels,
                    '--report', OUT / 'install.json', *sorted(wheels.glob('aimee_*.whl'))], env=env, check=True)
    subprocess.run([python, '-m', 'pip', 'check'], env=env, check=True)
    code = '''import importlib,sys,os
from pathlib import Path
from importlib.metadata import version
import aimee_native_runtime
root=Path(sys.prefix)
assert Path(aimee_native_runtime.__file__).resolve().is_relative_to(root)
for name in ['aimee_gemma4_12b','aimee_gemma4_26b','aimee_qwen3_8_27b']:
    module=importlib.import_module(name)
    assert Path(module.__file__).resolve().is_relative_to(root)
    assert importlib.import_module(name+'.worker') is importlib.import_module('aimee_native_runtime.worker')
assert os.access(Path(aimee_native_runtime.__file__).parent/'native/aimee-model-client',os.X_OK)
assert version('aimee-native-runtime')=='0.3.1'
'''
    checks = []
    subprocess.run([python, '-c', code], env=env, check=True)
    checks.append('fresh-coinstallation-shares-one-runtime')
    protected = {str(file.relative_to(site)): hashlib.sha256(file.read_bytes()).hexdigest()
                 for name in ('aimee_gemma4_12b', 'aimee_qwen3_8_27b', 'aimee_native_runtime')
                 for file in (site / name).rglob('*') if file.is_file() and file.suffix != '.pyc'}
    subprocess.run([python, '-m', 'pip', 'uninstall', '--yes', 'aimee-gemma4-26b'], env=env, check=True)
    assert not (site / 'aimee_gemma4_26b').exists()
    assert all(hashlib.sha256((site / file).read_bytes()).hexdigest() == digest for file, digest in protected.items())
    subprocess.run([python, '-m', 'pip', 'check'], env=env, check=True)
    for name in ('aimee-gemma4-12b', 'aimee-qwen3-8-27b'):
        subprocess.run([ENVIRONMENT / 'bin' / name, '--help'], env=env, check=True, capture_output=True)
    checks.append('uninstalling-one-model-preserves-other-models-and-runtime-bytes')
    subprocess.run([python, '-m', 'pip', 'install', '--no-index', '--find-links', wheels,
                    'aimee-gemma4-26b[gguf]==0.3.1'], env=env, check=True)
    subprocess.run([python, '-c', code], env=env, check=True)
    checks.append('reinstallation-restores-independent-model-plugin')
    report = {'status': 'passed', 'checks': checks, 'protected_files': len(protected),
              'scope': 'Fresh plugin installation with read-only dependency symlinks from the independently validated clean dependency environment. Does not replace clean dependency-resolution proof.'}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
