"""Compile the larger-model loader in the pinned runtime; no upstream edits.

Operator build helper. Output is a private binary overlay, not a release gate.
Run with --source pointing at gguf_loader.py inside a CPU-only build container.
"""
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    source = pathlib.Path(a.source).resolve()
    output = pathlib.Path(a.output).resolve()
    output.mkdir(exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='aimee-loader-build-') as tmp:
        root = pathlib.Path(tmp)
        package = root / 'aimee_vllm'
        package.mkdir()
        shutil.copy2(source, package / 'gguf_loader.py')
        (root / 'setup.py').write_text('''from setuptools import setup, Extension
from Cython.Build import cythonize
setup(ext_modules=cythonize([Extension('aimee_vllm.gguf_loader',
    ['aimee_vllm/gguf_loader.py'], extra_compile_args=['-O3', '-g0'],
    extra_link_args=['-s'])], compiler_directives={'language_level': 3,
    'binding': True, 'annotation_typing': False, 'embedsignature': False}))
''')
        with (output / 'build.log').open('w') as log:
            subprocess.run([sys.executable, 'setup.py', 'build_ext', '--inplace'],
                           cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)
        binaries = list(package.glob('gguf_loader.*.so'))
        if len(binaries) != 1:
            raise RuntimeError('expected one compiled loader')
        target = output / binaries[0].name
        shutil.copy2(binaries[0], target)
    report = {
        'status': 'compiled',
        'scope': 'Loader compilation only; real model and native-memory checks pending',
        'python': sys.version,
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'binary': target.name,
        'binary_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
    }
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
