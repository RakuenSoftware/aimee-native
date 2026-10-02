#!/usr/bin/env python3
"""Build the private host encoder as hardened CPython extensions; ship no source files."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from setuptools import Extension, setup
from Cython.Build import cythonize

MODULES = ('publisher', 'checkpoint_weights', 'gguf_weights', 'gemma_compile',
           'bounded_compile', 'local_compile')


def build(source, output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix='aimee-compiler-build-') as temporary:
        root = Path(temporary)
        package = root / 'aimee_vllm' / 'native_compiler'
        package.mkdir(parents=True)
        (root / 'aimee_vllm' / '__init__.py').write_bytes(b'')
        (package / '__init__.py').write_bytes(b'')
        extensions = []
        for name in MODULES:
            original = source / (name + '.py')
            if not original.is_file():
                raise FileNotFoundError(original)
            target = package / original.name
            shutil.copyfile(original, target)
            extensions.append(Extension(
                'aimee_vllm.native_compiler.' + name, [str(target)],
                extra_compile_args=['-O3', '-g0', '-fvisibility=hidden',
                                    '-ffunction-sections', '-fdata-sections'],
                extra_link_args=['-s', '-Wl,--gc-sections', '-Wl,--build-id=none']))
        old_cflags = os.environ.get('CFLAGS', '')
        os.environ['CFLAGS'] = old_cflags + ' -ffile-prefix-map=' + str(root) + '=/aimee-compiler'
        try:
            setup(name='aimee-native-compiler',
                  ext_modules=cythonize(
                      extensions,
                      compiler_directives={'language_level': '3', 'binding': False,
                                           'embedsignature': False, 'docstrings': False},
                      quiet=True, build_dir=str(root / 'cython')),
                  script_args=['build_ext', '--build-lib', str(root / 'build'),
                               '--build-temp', str(root / 'objects')],
                  options={'build_ext': {'inplace': False}})
        finally:
            os.environ['CFLAGS'] = old_cflags
        built = root / 'build' / 'aimee_vllm' / 'native_compiler'
        for name in MODULES:
            choices = list(built.glob(name + '.*.so'))
            if len(choices) != 1:
                raise RuntimeError('missing compiled native encoder: ' + name)
            target = output / choices[0].name
            shutil.copyfile(choices[0], target)
            subprocess.run([sys.executable, str(repo / 'distribution/release/harden-elf.py'),
                            str(target)], check=True)
        (output / '__init__.py').write_bytes(b'')
    if any(p.suffix in ('.pyx', '.c', '.cpp') or (p.suffix == '.py' and p.name != '__init__.py')
           for p in output.iterdir()):
        raise RuntimeError('private source escaped compiler build')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1] / 'service')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    build(a.source, a.output)
