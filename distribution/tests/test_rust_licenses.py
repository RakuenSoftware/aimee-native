import json,pathlib,subprocess,sys,tempfile,unittest

SCRIPT=pathlib.Path(__file__).resolve().parents[1]/'release/rust_licenses.py'
class Notices(unittest.TestCase):
 def test_only_reachable_packages_are_reported(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);packages=[]
   for name in ('private','linked','inactive'):
    p=root/name;p.mkdir();(p/'Cargo.toml').write_text('');(p/'LICENSE').write_text('test notice')
    packages.append({'id':name,'name':name,'version':'1.0.0','source':None if name=='private' else 'registry','manifest_path':str(p/'Cargo.toml'),'license':'MIT'})
   metadata={'packages':packages,'resolve':{'root':'private','nodes':[{'id':'private','deps':[{'pkg':'linked'}]},{'id':'linked','deps':[]},{'id':'inactive','deps':[]}]}}
   source=root/'metadata.json';source.write_text(json.dumps(metadata))
   command=[sys.executable,str(SCRIPT),str(source),'--notice',str(root/'notice'),'--report',str(root/'report')]
   subprocess.run(command,check=True,capture_output=True)
   self.assertEqual([p['name'] for p in json.loads((root/'report').read_text())['packages']],['linked'])
   metadata['resolve']['nodes'][0]['deps'].append({'pkg':'missing'})
   source.write_text(json.dumps(metadata))
   self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
if __name__=='__main__':unittest.main()
