from pathlib import Path
import sys,os,types,unittest,zipfile,hashlib,tarfile,json
nas=Path('/mnt/pve/backup/aimee-experiments/root-evacuation-20261005-r1/gemma-composition-candidate-r1')
root=nas/'broker-v2-local-build-r1'
wheel=root/'aimee_native_runtime-0.3.2+gemma.prefix.candidate4-cp312-cp312-linux_x86_64.whl'
assert hashlib.sha256(wheel.read_bytes()).hexdigest()=='1e6d6f30bf076f5ab9920b8c51c80fafb771b15bb167cdd2edf102d1af7aac38'
site=root/'candidate4-site';site.mkdir(exist_ok=False)
with zipfile.ZipFile(wheel) as z:z.extractall(site)
sys.path.insert(0,str(site))
os.environ['AIMEE_STORE_LIBRARY']='/opt/aimee-native-serving/clean-release-env-build2/lib/python3.12/site-packages/aimee_gemma4_12b/native/libaimee_native.so'
source=nas/'candidate3-python/gemma-candidate3-source.tar.gz'
assert hashlib.sha256(source.read_bytes()).hexdigest()=='1e507f3b83701f3d1f1c2eb533077322901d786d2a21d98f3287a7d7b95e4009'
suite=unittest.TestSuite()
test_hashes={}
with tarfile.open(source) as tf:
 for name in ['test_composition','test_preparation','test_admission','test_enrolled_authentication']:
  data=tf.extractfile('distribution/vllm/tests/'+name+'.py').read();test_hashes[name]=hashlib.sha256(data).hexdigest()
  module=types.ModuleType(name);sys.modules[name]=module
  exec(data.decode().replace('aimee_vllm','aimee_native_runtime'),module.__dict__)
  suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
result=unittest.TextTestRunner(verbosity=2).run(suite)
import aimee_native_runtime.composition as composition
assert composition.__file__.startswith(str(site)) and composition.__file__.endswith('.so')
assert result.testsRun==29 and not result.skipped
assert not __import__('torch').cuda.is_initialized()
print(json.dumps({'status':'passed' if result.wasSuccessful() else 'failed','tests':result.testsRun,'skips':len(result.skipped),'compiled_module':composition.__file__,'source_test_sha256':test_hashes,'cuda_initialized':False,'site_scope':'private NAS extracted candidate4 only; no deployment'},indent=2))
sys.exit(not result.wasSuccessful())
