#!/usr/bin/env python3
"""Build separately installable model plugins with isolated Rust libraries.

The Rust source directory supplies the pinned manifest, lockfile and native ABI
bridge. Repository adapter sources override that build snapshot.
Cython compiles vLLM framework glue; it does not implement model semantics.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

from model_plugin_layout import COMMON_MODULES, PUBLIC_MODULES, BINDING_SOURCE, shared_source, write_binding

MODELS = {
    "gemma4-12b": "aimee_gemma4_12b",
    "gemma4-26b": "aimee_gemma4_26b",
    "qwen3-8-27b": "aimee_qwen3_8_27b",
    "gemma4-e2b": "aimee_gemma4_e2b",
    "gemma4-e4b": "aimee_gemma4_e4b",
}


def build_shared_runtime(repo, output, version):
    env = dict(os.environ, CARGO_TARGET_DIR=os.environ.get('CARGO_TARGET_DIR', str(output / 'rust-target')))
    subprocess.run(['cargo', 'build', '--manifest-path', str(repo / 'distribution/launcher/Cargo.toml'),
                    '--locked', '--release', '--bin', 'aimee-model-client', '--features', 'model-plugin-client'],
                   env=env, check=True)
    with tempfile.TemporaryDirectory(prefix='aimee-native-runtime-') as temporary:
        root = Path(temporary)
        shutil.copyfile(repo / 'LICENSE', root / 'LICENSE')
        package = root / 'aimee_native_runtime'
        (package / 'native').mkdir(parents=True)
        (package / '__init__.py').write_text('"""Shared Rust enrollment, selection and lifecycle runtime."""\n')
        origin = repo / 'distribution/vllm/aimee_vllm'
        for module in (*COMMON_MODULES, *PUBLIC_MODULES):
            (package / (module + '.py')).write_text(shared_source(origin, module))
        (package / '_model.py').write_text(BINDING_SOURCE)
        shutil.copyfile(Path(env['CARGO_TARGET_DIR']) / 'release/aimee-model-client', package / 'native/aimee-model-client')
        (package / 'native/aimee-model-client').chmod(0o755)
        (root / 'setup.py').write_text(f'''from setuptools import setup, Extension
from Cython.Build import cythonize
setup(name='aimee-native-runtime',version={version!r},license='AGPL-3.0-only',license_files=['LICENSE'],url='https://github.com/RakuenSoftware/aimee-native',packages=['aimee_native_runtime'],
ext_modules=cythonize([Extension('aimee_native_runtime.'+name,['aimee_native_runtime/'+name+'.py'],extra_compile_args=['-O3','-g0'],extra_link_args=['-s']) for name in {list(COMMON_MODULES)!r}],compiler_directives={{'language_level':3,'binding':True,'annotation_typing':False}}))
''')
        subprocess.run([sys.executable, 'setup.py', 'build_ext', '--inplace'], cwd=root, check=True)
        for module in COMMON_MODULES:
            (package / (module + '.py')).unlink()
            (package / (module + '.c')).unlink()
        (root / 'setup.py').write_text(f'''from setuptools import setup, Distribution
class Binary(Distribution):
 def has_ext_modules(self): return True
setup(name='aimee-native-runtime',version={version!r},license='AGPL-3.0-only',license_files=['LICENSE'],url='https://github.com/RakuenSoftware/aimee-native',packages=['aimee_native_runtime'],
package_data={{'aimee_native_runtime':['native/*','*.so']}},distclass=Binary,python_requires='>=3.12')
''')
        subprocess.run([sys.executable, 'setup.py', 'bdist_wheel', '--dist-dir', str(output / 'wheels')], cwd=root, check=True)
    wheel = next((output / 'wheels').glob('aimee_native_runtime-' + version + '-*.whl'))
    return {'wheel': wheel.name, 'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest()}


def stage_rust_source(source, repo, rust):
    """Stage code inputs without copying caches, evidence or model data."""
    rust.mkdir()
    for name in ("Cargo.toml", "Cargo.lock"):
        shutil.copyfile(source / name, rust / name)
    toolchain = source / "rust-toolchain.toml"
    shutil.copyfile(toolchain if toolchain.exists() else repo / "rust-toolchain.toml",
                    rust / "rust-toolchain.toml")
    shutil.copytree(source / "native", rust / "native")
    shutil.copytree(repo / "src", rust / "src", dirs_exist_ok=True)
    shutil.copyfile(repo / "build.rs", rust / "build.rs")
    shutil.copyfile(repo / "native/vllm_runtime_portable.cpp", rust / "native/vllm_runtime_portable.cpp")


def build(model, package, source, output, version):
    repo = Path(__file__).resolve().parents[2]
    origin = repo / "distribution/vllm/aimee_vllm"
    with tempfile.TemporaryDirectory(prefix=package + "-") as temporary:
        root = Path(temporary)
        shutil.copyfile(repo / "LICENSE", root / "LICENSE")
        rust = root / "rust"
        stage_rust_source(source, repo, rust)
        manifest = rust / "Cargo.toml"
        text = manifest.read_text().replace('name = "aimee-qwen"', 'name = "aimee-native"')
        text = text.replace('license = "LicenseRef-Proprietary"', 'license = "AGPL-3.0-only"')
        lock = rust / "Cargo.lock"
        lock.write_text(lock.read_text().replace('name = "aimee-qwen"', 'name = "aimee-native"'))
        for name in MODELS:
            feature = "adapter-" + name
            if feature + " =" not in text:
                text = text.replace("[features]", "[features]\n" + feature + " = []")
        manifest.write_text(text)
        env = dict(os.environ, CARGO_TARGET_DIR=os.environ.get("CARGO_TARGET_DIR", str(output / "rust-target")),
                   PYTHON_INCLUDE=__import__("sysconfig").get_path("include"))
        subprocess.run(["cargo", "build", "--manifest-path", str(manifest), "--locked",
                        "--release", "--lib", "--no-default-features", "--features",
                        "vllm-portable,adapter-" + model], env=env, check=True)
        library = Path(env["CARGO_TARGET_DIR"]) / "release/libaimee_native.so"
        symbols = subprocess.check_output(["nm", "-D", str(library)], text=True)
        for name, candidate in MODELS.items():
            symbol = candidate.replace("aimee_", "aimee_", 1) + "_adapter"
            assert (symbol in symbols) == (name == model), "cross-model adapter leaked"
        pkg = root / package
        pkg.mkdir()
        write_binding(pkg)
        registration = (origin / "__init__.py").read_text().replace("aimee_vllm", package)
        registration = registration.replace('    from .compatibility', f'''    import os, json
    from pathlib import Path
    PLUGIN_NAME = {package!r}
    selected = os.environ.get("VLLM_PLUGINS", "").split(",")
    if selected != [PLUGIN_NAME]:
        return
    os.environ["AIMEE_NATIVE_PLUGIN_CONTRACT"] = str(Path(__file__).parent / "native/adapter.json")
    config = json.loads(Path(os.environ["AIMEE_VLLM_CONFIG"]).read_bytes())
    from .model_adapter import ModelAdapter
    ModelAdapter(config)
    from .compatibility''', 1)
        if model in ("gemma4-e2b", "gemma4-e4b"):
            shutil.copyfile(repo / "distribution/release/small_model_capture.py", pkg / "small_model_capture.py")
            registration = registration.replace('    ModelAdapter(config)\n',
                '    ModelAdapter(config)\n    from .small_model_capture import install\n    install()\n')
            shutil.copyfile(repo / "distribution/release/small_model_gguf.py", pkg / "small_model_gguf.py")
            registration = registration.replace('from .gguf_loader import register as register_gguf',
                                                'from .small_model_gguf import register as register_gguf')
        (pkg / "__init__.py").write_text(registration)
        native = pkg / "native"
        native.mkdir()
        shutil.copyfile(library, native / "libaimee_native.so")
        (native / "adapter.json").write_text(json.dumps({"adapter": model, "python_module": package, "adapter_symbol": package + "_adapter", "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(), "positioning": "native-prefix-absolute-v1"}) + "\n")
        # Only the binding and dedicated Rust library ship in a model wheel.
        (root / "setup.py").write_text(f'''from setuptools import setup, Distribution
class Binary(Distribution):
 def has_ext_modules(self): return True
setup(name={package.replace('_','-')!r},version={version!r},license='AGPL-3.0-only',license_files=['LICENSE'],url='https://github.com/RakuenSoftware/aimee-native',packages=[{package!r}],package_data={{{package!r}:['native/*']}},distclass=Binary,
entry_points={{'vllm.general_plugins':[{package+'='+package+':register'!r}],'console_scripts':[{package.replace('_','-')+'='+package+'.cli:main'!r}]}},install_requires=['vllm==0.30.0','aimee-native-runtime=={version}'],python_requires='>=3.12')
''')
        subprocess.run([sys.executable, "setup.py", "bdist_wheel", "--dist-dir", str(output / "wheels")], cwd=root, check=True)
        wheel = next((output / "wheels").glob(package + "-" + version + "-*.whl"))
        with zipfile.ZipFile(wheel) as z:
            assert all(n.startswith((package + "/", package + "-")) for n in z.namelist())
            assert not any("native_compiler/" in n or n.endswith((".c", ".cpp", ".pyx", ".gguf", ".safetensors")) for n in z.namelist())
        return {"adapter": model, "wheel": wheel.name, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(), "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rust-source", type=Path, default=Path(__file__).resolve().parents[2],
                   help="Rust manifest/native inputs; defaults to this repository")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--version", default="0.3.3")
    a = p.parse_args()
    output = a.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    runtime = build_shared_runtime(Path(__file__).resolve().parents[2], output, a.version)
    reports = [build(model, package, a.rust_source.resolve(), output, a.version)
               for model, package in MODELS.items()]
    (output / "manifest.json").write_text(json.dumps({"schema": 1, "shared_runtime": runtime, "plugins": reports}, indent=2) + "\n")


if __name__ == "__main__":
    main()
