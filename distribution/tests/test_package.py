import importlib.util
import hashlib
import json
import pathlib
import subprocess
import tempfile
import unittest

script=pathlib.Path(__file__).resolve().parents[1]/'release/package.py'
spec=importlib.util.spec_from_file_location('release_package',script)
pkg=importlib.util.module_from_spec(spec);spec.loader.exec_module(pkg)
class PackageTests(unittest.TestCase):
    def test_only_client_files_allowed(self):
        for p in ['src/encoding.rs','bin/aimee-prepare','lib/../private.so','models/key.pem','research/result.json']:
            self.assertFalse(pkg.allowed(p),p)
        for p in ['bin/aimee-vllm','lib/libaimee_native.so','lib/libamdhip64.so.7','models/gemma.gguf','licenses/vllm.txt','runtime/image.json']:
            self.assertTrue(pkg.allowed(p),p)
    def test_signed_explicit_package_and_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);key=root/'fixture.key';pub=root/'fixture.pub'
            subprocess.run(['openssl','genpkey','-algorithm','ED25519','-out',str(key)],check=True,capture_output=True)
            subprocess.run(['openssl','pkey','-in',str(key),'-pubout','-out',str(pub)],check=True,capture_output=True)
            files={}
            for name in ['bin/aimee-vllm','lib/libaimee_native.so','models/test.gguf']:
                path=root/'input'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture, not an executable release');files[name]=str(path)
            descriptor=root/'image.json';descriptor.write_text(json.dumps({'image':'registry.example/aimee@sha256:'+'a'*64,'model_config':'models/config.json'}))
            sidecar=root/'config.json';sidecar.write_text('{}')
            files['runtime/image.json']=str(descriptor);files['models/config.json']=str(sidecar)
            evidence=root/'test-only-gate.json' ;evidence.write_text(json.dumps({'status':'passed','runtime_commit':'a'*40,'model':'test','artifact_set_sha256':pkg.artifact_set_digest([{'path':n,'bytes':pathlib.Path(p).stat().st_size,'sha256':hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest(),'executable':n=='bin/aimee-vllm'} for n,p in files.items()])}))
            plan={'manifest':{'runtime_commit':'a'*40,'model':'test','model_file':'models/test.gguf'},'files':files,'gate_evidence':{g:str(evidence) for g in pkg.GATES}}
            output=root/'release';pkg.package(plan,output,key)
            subprocess.run(['openssl','pkeyutl','-verify','-rawin','-pubin','-inkey',str(pub),'-in',str(output/'manifest.json'),'-sigfile',str(output/'manifest.sig')],check=True,capture_output=True)
            self.assertFalse((output/'fixture.key').exists());self.assertFalse((output/'test-only-gate.json').exists())
            sidecar.write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError,'exact release artifacts'):pkg.package(plan,root/'stale-evidence',key)
            self.assertFalse((root/'stale-evidence').exists())
            lab_plan=dict(plan,manifest=dict(plan['manifest'],model='lab-test'))
            lab=pkg.package(lab_plan,root/'lab-release',key,lab_only=True)
            self.assertEqual(lab['gates'],['lab_only'])
            settings=json.loads(descriptor.read_text())
            settings.update(gguf_matrix_backend='triton',mm_proj='models/projector.gguf')
            descriptor.write_text(json.dumps(settings))
            with self.assertRaisesRegex(ValueError,'signed GGUF projector'):
                pkg.package(lab_plan,root/'missing-projector',key,lab_only=True)
            projector=root/'projector.gguf';projector.write_bytes(b'fixture projector')
            files['models/projector.gguf']=str(projector)
            larger=pkg.package(lab_plan,root/'larger-release',key,lab_only=True)
            saved=json.loads((root/'larger-release/runtime/image.json').read_text())
            self.assertEqual(saved['gguf_matrix_backend'],'triton')
            self.assertIn('models/projector.gguf',[a['path'] for a in larger['artifacts']])
            subprocess.run(['openssl','pkeyutl','-verify','-rawin','-pubin','-inkey',str(pub),'-in',str(root/'larger-release/manifest.json'),'-sigfile',str(root/'larger-release/manifest.sig')],check=True,capture_output=True)
            for invalid in ({'gguf_matrix_backend':'typo'}, {'mm_proj':'models/../projector.gguf'}, {'extra':True}):
                descriptor.write_text(json.dumps(dict(settings,**invalid)))
                with self.assertRaises(ValueError):
                    pkg.package(lab_plan,root/'invalid-settings',key,lab_only=True)
            descriptor.write_text(json.dumps(settings))
            with self.assertRaisesRegex(ValueError,'lab model identity'):pkg.package(plan,root/'not-lab',key,lab_only=True)
            evidence.write_text(json.dumps({'status':'pending','runtime_commit':'a'*40,'model':'test'}))
            with self.assertRaises(ValueError):pkg.package(plan,root/'rejected',key)
            self.assertFalse((root/'rejected').exists())
if __name__=='__main__':unittest.main()
