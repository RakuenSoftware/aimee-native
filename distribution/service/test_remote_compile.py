import json,pathlib,struct,subprocess,sys,tempfile,unittest
SCRIPT=pathlib.Path(__file__).with_name('remote_compile.py')
class Transport(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name)
  fake=self.root/'compiler.py';fake.write_text("import argparse,pathlib,sys\np=argparse.ArgumentParser();p.add_argument('--output');p.add_argument('--identity');p.add_argument('--key');a=p.parse_args();r=pathlib.Path(a.output);r.mkdir();(r/'index.json').write_bytes(b'{\\\"verified_later\\\":true}');(r/'compact.pack').write_bytes(bytes(range(256))*10000)\n")
  worker=self.root/'worker.json';worker.write_text(json.dumps({'model_revision':'gemma','state':str(self.root/'state'),'library':'/not-used','compiler':[sys.executable,str(fake)]}));worker.chmod(0o600)
  self.config=self.root/'front.json';self.config.write_text(json.dumps({'command':[sys.executable,str(SCRIPT),'worker','--config',str(worker)]}));self.config.chmod(0o600)
  self.request={'identity':{'model_revision':'gemma'},'response':{}}
 def run_front(self,identity='gemma'):
  return subprocess.run([sys.executable,str(SCRIPT),'frontend','--config',str(self.config),'--output',str(self.root/'result'),'--identity',identity,'--key','a'*64],input=json.dumps(self.request).encode(),capture_output=True)
 def test_streams_complete_artifacts(self):
  p=self.run_front();self.assertEqual(p.returncode,0,p.stderr.decode());self.assertEqual((self.root/'result/compact.pack').read_bytes(),bytes(range(256))*10000)
  self.assertEqual(json.loads((self.root/'result/index.json').read_text()),{'verified_later':True})
 def test_wrong_model_rejected(self):
  self.assertNotEqual(self.run_front('other').returncode,0);self.assertFalse((self.root/'result/compact.pack').exists())
 def test_oversized_reply_rejected_before_artifact_write(self):
  code="import sys;sys.stdout.buffer.write("+repr(b'AMCP1'+struct.pack('!QQ',1,2**40))+")"
  self.config.write_text(json.dumps({'command':[sys.executable,'-c',code]}))
  self.assertNotEqual(self.run_front().returncode,0);self.assertFalse((self.root/'result/compact.pack').exists())
 def test_existing_artifact_not_overwritten(self):
  r=self.root/'result';r.mkdir();(r/'index.json').write_bytes(b'existing')
  self.assertNotEqual(self.run_front().returncode,0);self.assertEqual((r/'index.json').read_bytes(),b'existing')
 def test_writable_config_rejected(self):
  self.config.chmod(0o666);self.assertNotEqual(self.run_front().returncode,0)
if __name__=='__main__':unittest.main()
