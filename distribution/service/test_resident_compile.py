import json
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

SERVICE = pathlib.Path(__file__).parent


class ResidentTransport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.socket = self.root / 'compiler.sock'
        script = self.root / 'server.py'
        script.write_text('''import sys,pathlib,json
sys.path.insert(0,sys.argv[1])
from resident_compile import serve
class Compiler:
 def __init__(self):self.jobs=0
 def compile(self,request,output,identity,key):
  if request.get('fail'):raise ValueError('expected failure')
  self.jobs+=1;output.mkdir()
  (output/'index.json').write_text(json.dumps({'jobs':self.jobs}))
  (output/'compact.pack').write_bytes(json.dumps(request['response']['facts']).encode()*1000)
serve({'model_revision':'gemma','state':sys.argv[2],'position_policy':'negative','encoding_revision':'fixture-v1'},sys.argv[3],Compiler())
''')
        self.server = subprocess.Popen([sys.executable, str(script), str(SERVICE), str(self.root / 'state'), str(self.socket)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.addCleanup(self.stop)
        for _ in range(200):
            if self.socket.exists():break
            if self.server.poll() is not None:self.fail(self.server.stderr.read().decode())
            time.sleep(.01)
        else:self.fail('resident fixture did not start')
        worker = self.root / 'worker.json'
        worker.write_text(json.dumps({'model_revision':'gemma','resident_socket':str(self.socket)}))
        self.front = self.root / 'front.json'
        self.front.write_text(json.dumps({'command':[sys.executable,str(SERVICE/'remote_compile.py'),'worker','--config',str(worker)]}))
        self.counter = 0

    def stop(self):
        self.server.terminate()
        self.server.wait(timeout=5)
        self.server.stderr.close()

    def call(self, facts, fail=False, identity='gemma', position='negative', encoding='fixture-v1'):
        self.counter += 1
        output = self.root / ('result'+str(self.counter))
        request = {'identity':{'model_revision':identity,'position_policy':position,'encoding_revision':encoding},'response':{'facts':facts},'fail':fail}
        result = subprocess.run([sys.executable,str(SERVICE/'remote_compile.py'),'frontend','--config',str(self.front),'--output',str(output),'--identity',identity,'--key','a'*64],input=json.dumps(request).encode(),capture_output=True,timeout=10)
        return result, output

    def test_model_owner_reused_complete_order_retained_and_failure_recovers(self):
        for jobs, facts in [(1,['first','second','third']),(2,['third','second','first'])]:
            result, out = self.call(facts)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(json.loads((out/'index.json').read_text())['jobs'],jobs)
            self.assertEqual((out/'compact.pack').read_bytes(),json.dumps(facts).encode()*1000)
        result,_ = self.call(['bad'],fail=True)
        self.assertNotEqual(result.returncode,0)
        result,out = self.call(['next'])
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertEqual(json.loads((out/'index.json').read_text())['jobs'],3)
        self.assertEqual(list((self.root/'state').iterdir()),[])

    def test_wrong_model_cannot_reach_resident_compiler(self):
        result,_ = self.call(['wrong'],identity='other')
        self.assertNotEqual(result.returncode,0)
        result,out = self.call(['right'])
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertEqual(json.loads((out/'index.json').read_text())['jobs'],1)

    def test_wrong_preparation_policy_rejected_before_compile_and_next_request_recovers(self):
        for kwargs in ({'position': 'nonnegative'}, {'encoding': 'other-v2'}):
            result, _ = self.call(['wrong'], **kwargs)
            self.assertNotEqual(result.returncode, 0)
        result, out = self.call(['right'])
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(json.loads((out/'index.json').read_text())['jobs'], 1)


class PreparationProfile(unittest.TestCase):
    def test_larger_model_policy_reaches_compiler_without_changing_legacy_default(self):
        from unittest.mock import Mock, patch
        from types import SimpleNamespace
        from resident_compile import build_compiler
        bounded = Mock()
        legacy = Mock()
        with patch.dict(sys.modules, {'bounded_compile': SimpleNamespace(BoundedTextCompiler=bounded),
                                      'gemma_compile': SimpleNamespace(GemmaCompiler=legacy)}):
            build_compiler({'model': '/qwen', 'preparation_backend': 'bounded_text_fp32',
                            'position_policy': 'negative'})
            bounded.assert_called_once_with('/qwen', 1024, 12, None, 'float32', memory_positions='negative')
            build_compiler({'model': '/gemma12'})
            legacy.assert_called_once_with('/gemma12', 1024, 12, None, 'bfloat16')


if __name__ == '__main__':
    unittest.main()
