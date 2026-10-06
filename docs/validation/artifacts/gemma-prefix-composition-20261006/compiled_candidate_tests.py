from pathlib import Path
import sys,os,types,unittest
root=Path('/opt/jmlr-second-review-20261005/repair-cache/gemma-composition-candidate-r1')
sys.path.insert(0,str(root/'candidate-site'))
os.environ['AIMEE_STORE_LIBRARY']='/opt/aimee-native-serving/clean-release-env-build2/lib/python3.12/site-packages/aimee_gemma4_12b/native/libaimee_native.so'
names=['test_composition','test_preparation','test_admission','test_enrolled_authentication']
suite=unittest.TestSuite()
for name in names:
 module=types.ModuleType(name);sys.modules[name]=module
 text=(root/'source/distribution/vllm/tests'/ (name+'.py')).read_text().replace('aimee_vllm','aimee_native_runtime')
 exec(text,module.__dict__)
 suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
result=unittest.TextTestRunner(verbosity=2).run(suite)
import aimee_native_runtime.composition as composition
print('Loaded candidate composition:',composition.__file__)
assert composition.__file__.startswith(str(root/'candidate-site')) and composition.__file__.endswith('.so')
sys.exit(not result.wasSuccessful())
