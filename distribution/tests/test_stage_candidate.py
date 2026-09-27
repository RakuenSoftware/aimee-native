import hashlib,json,pathlib,subprocess,sys,tempfile,unittest

class CandidateStage(unittest.TestCase):
 def stage(self,corrupt=False):
  with tempfile.TemporaryDirectory() as tmp:
   r=pathlib.Path(tmp);installed=r/'installed';release=installed/'releases/old';release.mkdir(parents=True);inputs=r/'inputs';inputs.mkdir();candidate=r/'candidate'
   (installed/'active.json').write_text('{"current":"old"}')
   (installed/'config.json').write_text(json.dumps({'memory_root':str(installed/'memory'),'token_file':'/existing/restricted/token'}))
   (release/'manifest.json').write_text('{"schema":1}')
   model=release/'models/model.gguf';model.parent.mkdir();model.write_bytes(b'fixture model')
   (inputs/'image.json').write_text('{"image":"fixture"}');(inputs/'profile.json').write_text('{"schema":1}')
   artifacts=[]
   for name,p in [('models/model.gguf',model),('runtime/image.json',inputs/'image.json'),('runtime/profile.json',inputs/'profile.json')]:artifacts.append({'path':name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'executable':False})
   identity=hashlib.sha256(json.dumps(sorted(artifacts,key=lambda x:x['path']),sort_keys=True,separators=(',',':')).encode()).hexdigest()
   (inputs/'expected-artifacts.json').write_text(json.dumps({'artifacts':artifacts,'artifact_set_sha256':identity}))
   if corrupt:model.write_bytes(b'corrupt model')
   p=subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('stage_candidate.py')),'--installed-root',str(installed),'--candidate-root',str(candidate),'--inputs',str(inputs)],capture_output=True,text=True)
   self.assertEqual(json.loads((installed/'active.json').read_text()),{'current':'old'})
   if corrupt:
    self.assertNotEqual(p.returncode,0);self.assertFalse((candidate/'active.json').exists());return
   self.assertEqual(p.returncode,0,p.stderr)
   a=json.loads((candidate/'active.json').read_text());m=json.loads((candidate/'releases'/a['current']/'manifest.json').read_text());self.assertEqual(m['gates'],['lab_only'])
   self.assertEqual(json.loads((candidate/'config.json').read_text())['memory_root'],str(candidate/'memory'))
   self.assertEqual(json.loads((candidate/'staging-report.json').read_text())['artifact_set_sha256'],identity)
 def test_exact_artifacts_isolated_from_normal_installation(self):self.stage()
 def test_corruption_cannot_activate_candidate(self):self.stage(corrupt=True)

if __name__=='__main__':unittest.main()
