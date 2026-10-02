#!/usr/bin/env python3
"""Private build: compile client modules; omit encoding, JIT source and fixtures.
Run in the pinned runtime's Python with Cython/setuptools/wheel installed.
"""
import argparse,os,pathlib,shutil,subprocess,sys,tempfile,zipfile
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--version',default='0.2.2');a=p.parse_args()
repo=pathlib.Path(__file__).resolve().parents[2];out=pathlib.Path(a.output).resolve();out.mkdir(parents=True,exist_ok=True)
module_pairs=[
 ('stream_completion','_p0'),('selection','_p1'),('gguf_loader','_p2'),('control','_p3'),
 ('admission','_p4'),('backend','_p5'),('binary_kernel','_p6'),('cache','_p7'),
 ('cache_identity','_p8'),('cli','_p9'),('state','_p10'),('store','_p11'),
 ('worker','_p12'),('runtime_ops','_p13'),('runtime_owner','_p14'),('compatibility','_p15')]
modules=[opaque for _,opaque in module_pairs]
module_map=dict(module_pairs)
class_map={
 'AimeeMetadataBuilder':'B0','AimeeAttentionBackend':'B1','AimeeAttentionImpl':'B2',
 'AimeeWorker':'W0','NativeAdmission':'M0',
}
def rewrite(content):
 for old,new in sorted(module_pairs,key=lambda pair:len(pair[0]),reverse=True):
  content=content.replace('from . import '+old,'from . import '+new+' as '+old)
  content=content.replace('from .'+old,'from .'+new)
  content=content.replace('aimee_vllm.'+old+'.','aimee_vllm.'+new+'.')
 for old,new in class_map.items():content=content.replace(old,new)
 # Keep the GGUF configuration key at runtime without embedding its complete
 # internal identifier in a distributed extension.
 content=content.replace("'gguf_weights'", "('gguf' + chr(95) + 'weights')")
 content=content.replace("'publisher UID mismatch'", "'writer UID mismatch'")
 return content
with tempfile.TemporaryDirectory(prefix='aimee-client-build-') as tmp:
 root=pathlib.Path(tmp);pkg=root/'aimee_vllm';pkg.mkdir()
 source=repo/'distribution/vllm/aimee_vllm'
 init=rewrite((source/'__init__.py').read_text())
 (pkg/'__init__.py').write_text(init)
 for name,opaque in module_pairs:
  target=pkg/(opaque+'.py')
  target.write_text(rewrite((source/(name+'.py')).read_text()))
 # Release-only import retargeting keeps readable private source while exposing
 # only opaque Triton module/function names in the customer wheel.
 backend=(pkg/(module_map['backend']+'.py'));backend.write_text(backend.read_text().replace(
  'from .kernel import native_attention','from ._k import k0').replace('native_attention[','k0['))
 runtime=(pkg/(module_map['runtime_ops']+'.py'));runtime.write_text(runtime.read_text().replace(
  'from .decoder_kernel import decode_words, decode_escapes',
  'from ._d import d0 as decode_words, d1 as decode_escapes').replace(
  'table0, table1, BLOCK=256)', 'table0, table1, a5=256)').replace(
  'words, exceptions, BLOCK=256)', 'words, exceptions, a5=256)'))
 subprocess.run([sys.executable,str(repo/'distribution/release/obfuscate-triton.py'),
                 str(source/'kernel.py'),str(pkg/'_k.py'),
                 '--functions','native_attention=k0'],check=True)
 subprocess.run([sys.executable,str(repo/'distribution/release/obfuscate-triton.py'),
                 str(source/'decoder_kernel.py'),str(pkg/'_d.py'),
                 '--functions','decode_words=d0,decode_escapes=d1'],check=True)
 (root/'setup.py').write_text('''from setuptools import setup,Extension
from Cython.Build import cythonize
from Cython.Compiler import Options
Options.docstrings = False
setup(name='aimee-vllm',version='''+repr(a.version)+''',packages=['aimee_vllm'],
 ext_modules=cythonize([Extension('aimee_vllm.'+m,['aimee_vllm/'+m+'.py'],extra_compile_args=['-O3','-g0','-fvisibility=hidden','-fno-ident','-fno-record-gcc-switches','-ffunction-sections','-fdata-sections','-flto'],extra_link_args=['-s','-flto','-Wl,--gc-sections','-Wl,--build-id=none','-Wl,--exclude-libs,ALL']) for m in '''+repr(modules)+'''],compiler_directives={'language_level':3,'binding':False,'annotation_typing':False,'embedsignature':False}),
 entry_points={'vllm.general_plugins':['aimee_native=aimee_vllm:register'],'console_scripts':['aimee-vllm=aimee_vllm._p9:main']},
 install_requires=['vllm>=0.30.0,<0.31'],python_requires='>=3.12')
''')
 env=dict(os.environ);env['CFLAGS']=env.get('CFLAGS','')+' -ffile-prefix-map='+str(root)+'=/aimee-client'
 subprocess.run([sys.executable,'setup.py','build_ext','--inplace'],cwd=root,env=env,check=True)
 for artifact in pkg.glob('*.so'):
  subprocess.run([sys.executable,str(repo/'distribution/release/harden-elf.py'),str(artifact)],check=True)
 for name in modules:
  (pkg/(name+'.py')).unlink();(pkg/(name+'.c')).unlink()
 (root/'setup.py').write_text('''from setuptools import setup,Distribution
class BinaryDistribution(Distribution):
 def has_ext_modules(self):return True
setup(name='aimee-vllm',version='''+repr(a.version)+''',packages=['aimee_vllm'],package_data={'aimee_vllm':['*.so']},
 entry_points={'vllm.general_plugins':['aimee_native=aimee_vllm:register'],'console_scripts':['aimee-vllm=aimee_vllm._p9:main']},
 install_requires=['vllm>=0.30.0,<0.31'],python_requires='>=3.12',
 distclass=BinaryDistribution)
''')
 subprocess.run([sys.executable,'setup.py','bdist_wheel','--dist-dir',str(out)],cwd=root,env=env,check=True)
 wheels=list(out.glob('aimee_vllm-'+a.version+'-*.whl'));assert len(wheels)==1,'use an empty output directory'
 with zipfile.ZipFile(wheels[0]) as wheel:
  names=wheel.namelist()
  assert all(not n.endswith(('.py','.pyc','.c','.pyx')) or n in ('aimee_vllm/__init__.py','aimee_vllm/_k.py','aimee_vllm/_d.py') for n in names)
  assert all(sum(n.startswith('aimee_vllm/'+m+'.') and n.endswith('.so') for n in names)==1 for m in modules)
  assert not any('/export_kernel.' in n or '/tests/' in n for n in names)
 print(wheels[0])
