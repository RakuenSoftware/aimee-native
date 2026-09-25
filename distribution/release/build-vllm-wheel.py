#!/usr/bin/env python3
"""Private build: compile client modules; omit encoding, JIT source and fixtures.
Run in the pinned runtime's Python with Cython/setuptools/wheel installed.
"""
import argparse,os,pathlib,shutil,subprocess,sys,tempfile,zipfile
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
repo=pathlib.Path(__file__).resolve().parents[2];out=pathlib.Path(a.output).resolve();out.mkdir(parents=True,exist_ok=True)
modules=['gguf_loader','control','admission','backend','binary_kernel','cache','cli','state','store','worker']
with tempfile.TemporaryDirectory(prefix='aimee-client-build-') as tmp:
 root=pathlib.Path(tmp);pkg=root/'aimee_vllm';pkg.mkdir()
 source=repo/'distribution/vllm/aimee_vllm'
 shutil.copyfile(source/'__init__.py',pkg/'__init__.py')
 for name in modules:shutil.copyfile(source/(name+'.py'),pkg/(name+'.py'))
 # Binary-only build must never silently fall back to private JIT source.
 backend=pkg/'backend.py';text=backend.read_text();start=text.index('else:\n    from .kernel');end=text.index('\n\nclass AimeeMetadataBuilder',start)
 text=text[:start]+"else:\n    raise RuntimeError('certified native kernel bank required')"+text[end:]
 start=text.index('        if os.environ.get("AIMEE_EXPORT_KERNELS"):');end=text.index('        return output',start)
 text=text[:start]+text[end:];backend.write_text(text)
 (root/'setup.py').write_text('''from setuptools import setup,Extension
from Cython.Build import cythonize
setup(name='aimee-vllm',version='0.1.0',packages=['aimee_vllm'],
 ext_modules=cythonize([Extension('aimee_vllm.'+m,['aimee_vllm/'+m+'.py'],extra_compile_args=['-O3','-g0'],extra_link_args=['-s']) for m in '''+repr(modules)+'''],compiler_directives={'language_level':3,'binding':True,'annotation_typing':False,'embedsignature':False}),
 entry_points={'vllm.general_plugins':['aimee_native=aimee_vllm:register'],'console_scripts':['aimee-vllm=aimee_vllm.cli:main']},
 install_requires=['vllm==0.30.0'],python_requires='>=3.12')
''')
 env=dict(os.environ);env['CFLAGS']=env.get('CFLAGS','')+' -ffile-prefix-map='+str(root)+'=/aimee-client'
 subprocess.run([sys.executable,'setup.py','build_ext','--inplace'],cwd=root,env=env,check=True)
 # Cython compiled from .py; remove every private source/generated C before wheel assembly.
 for name in modules:
  (pkg/(name+'.py')).unlink();(pkg/(name+'.c')).unlink()
 # No ext_modules rebuild: stage already compiled .so files as explicit data.
 (root/'setup.py').write_text('''from setuptools import setup,Distribution
class BinaryDistribution(Distribution):
 def has_ext_modules(self):return True
setup(name='aimee-vllm',version='0.1.0',packages=['aimee_vllm'],package_data={'aimee_vllm':['*.so']},
 entry_points={'vllm.general_plugins':['aimee_native=aimee_vllm:register'],'console_scripts':['aimee-vllm=aimee_vllm.cli:main']},
 install_requires=['vllm==0.30.0'],python_requires='>=3.12',
 distclass=BinaryDistribution)
''')
 subprocess.run([sys.executable,'setup.py','bdist_wheel','--dist-dir',str(out)],cwd=root,env=env,check=True)
 wheels=list(out.glob('aimee_vllm-0.1.0-*.whl'));assert len(wheels)==1,'use an empty output directory'
 with zipfile.ZipFile(wheels[0]) as wheel:
  names=wheel.namelist()
  assert all(not n.endswith(('.py','.pyc','.c','.pyx')) or n=='aimee_vllm/__init__.py' for n in names)
  assert all(sum(n.startswith('aimee_vllm/'+m+'.') and n.endswith('.so') for n in names)==1 for m in modules)
  assert not any('/kernel.' in n or '/export_kernel.' in n or '/tests/' in n for n in names)
 print(wheels[0])
