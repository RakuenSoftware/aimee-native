#!/usr/bin/env python3
"""Build the complete portable client on a CPU builder with CPython and Rust.

Requires Cython/setuptools/wheel and a C++ compiler only on the private builder.
No model, GPU toolkit, GPU architecture, PyTorch headers or GPU driver required.
"""
import argparse,json,os,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--gguf-source',type=Path,required=True)
p.add_argument('--download-base',required=True)
p.add_argument('--notices',type=Path,required=True)
p.add_argument('--version',default='0.2.2')
a=p.parse_args()
p.error('Shared-plugin building is retired; use build-model-plugins.py')
repo=Path(__file__).resolve().parents[2];out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
env=dict(os.environ,CARGO_TARGET_DIR=str(out/'target'))
def run(*args):subprocess.run(list(map(str,args)),cwd=repo,env=env,check=True)
run('sh',repo/'distribution/release/build-portable-client.sh')
run(sys.executable,repo/'distribution/release/build-vllm-wheel.py','--output',out/'modules','--version',a.version)
run(sys.executable,repo/'distribution/release/build-portable-gguf-wheel.py',a.gguf_source.resolve(),out/'gguf')
dep=json.loads((out/'gguf/dependency.json').read_text())
compiler_args=[]
if tuple(map(int,a.version.split('.')[:3])) >= (0,2,3):
    run(sys.executable,repo/'distribution/release/build-local-compiler.py',
        '--output',out/'compiler')
    compiler_args=['--compiler-dir',out/'compiler']
run(sys.executable,repo/'distribution/release/assemble-portable-wheel.py','--wheel',next((out/'modules').glob('*.whl')),'--launcher',out/'target/release/aimee-native','--library',out/'target/release/libaimee_qwen.so','--notices',a.notices.resolve(),'--output',out/'release','--gguf-wheel-url',a.download_base.rstrip('/')+'/'+dep['file'],'--gguf-wheel-sha256',dep['sha256'],'--version',a.version,*compiler_args)
run(sys.executable,repo/'distribution/release/audit-plugin-wheel.py',next((out/'release').glob('*.whl')),'--output',out/'wheel-audit.json')
