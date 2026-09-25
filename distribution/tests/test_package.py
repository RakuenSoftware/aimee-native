import importlib.util
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
            evidence=root/'test-only-gate.json' ;evidence.write_text(json.dumps({'status':'passed','runtime_commit':'a'*40,'model':'test'}))
            plan={'manifest':{'runtime_commit':'a'*40,'model':'test','model_file':'models/test.gguf'},'files':files,'gate_evidence':{g:str(evidence) for g in pkg.GATES}}
            output=root/'release';pkg.package(plan,output,key)
            subprocess.run(['openssl','pkeyutl','-verify','-rawin','-pubin','-inkey',str(pub),'-in',str(output/'manifest.json'),'-sigfile',str(output/'manifest.sig')],check=True,capture_output=True)
            self.assertFalse((output/'fixture.key').exists());self.assertFalse((output/'test-only-gate.json').exists())
            evidence.write_text(json.dumps({'status':'pending','runtime_commit':'a'*40,'model':'test'}))
            with self.assertRaises(ValueError):pkg.package(plan,root/'rejected',key)
            self.assertFalse((root/'rejected').exists())
if __name__=='__main__':unittest.main()
