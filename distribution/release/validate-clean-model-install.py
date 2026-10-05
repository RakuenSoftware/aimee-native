#!/usr/bin/env python3
"""Install release wheels into a new, independent environment on the validation host.

No inherited site-packages, PYTHONPATH, CUDA runtime symlinks or source checkout.
An installation failure is retained as a failed release gate, never a skip.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheels', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--environment', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    wheels = sorted(p for p in args.wheels.glob('aimee_*.whl') if not p.name.startswith('aimee_native_runtime-'))
    if len(wheels) != 3:
        raise ValueError('exactly three release candidates required')
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'AIMEE_VLLM_CONFIG', 'VLLM_PLUGINS'):
        env.pop(key, None)
    env.update(PIP_CACHE_DIR=str(args.output / 'pip-cache'), PYTHONNOUSERSITE='1')
    report = {'status': 'running', 'started': time.time(), 'phases': [],
              'wheels': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in wheels}}

    def run(name, command):
        with (args.output / (name + '.log')).open('xb') as log:
            completed = subprocess.run(list(map(str, command)), env=env,
                                       cwd=args.output, stdout=log, stderr=subprocess.STDOUT)
        report['phases'].append({'name': name, 'returncode': completed.returncode})
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        if completed.returncode:
            raise RuntimeError(name + ' failed; see preserved log')

    try:
        if args.environment.exists():
            raise ValueError('validation environment must not already exist')
        run('create-environment', [sys.executable, '-m', 'venv', args.environment])
        python = args.environment / 'bin/python'
        requirements = [str(p) + ('[gguf]' if 'gemma' in p.name else '') for p in wheels]
        run('install', [python, '-m', 'pip', 'install', '--find-links', args.wheels,
                        '--report', args.output / 'installation.json', *requirements])
        run('dependency-check', [python, '-m', 'pip', 'check'])
        run('inventory', [python, '-m', 'pip', 'inspect'])
        for package in ('aimee_gemma4_12b', 'aimee_gemma4_26b', 'aimee_qwen3_8_27b'):
            run(package + '-console', [args.environment / 'bin' / package.replace('_', '-'), '--help'])
            run(package + '-imports', [python, '-c',
                f'import importlib; from pathlib import Path; '
                f'm=importlib.import_module("{package}"); '
                'assert Path(m.__file__).resolve().is_relative_to(Path(__import__("sys").prefix)); '
                f'importlib.import_module("{package}.worker"); '
                f'importlib.import_module("{package}.model_adapter")'])
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        report['finished'] = time.time()
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
