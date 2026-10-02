"""Reject dependency substitution before assembling a client build context."""
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

SOURCE = pathlib.Path(__file__).resolve().parents[1] / 'container'

class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.script = self.root / 'builder'
        self.script.mkdir()
        for name in ('context.py', 'Dockerfile'):
            shutil.copyfile(SOURCE / name, self.script / name)
        (self.script / 'licenses').mkdir()
        (self.script / 'os-packages.lock').write_text('openssl=3.0.2-0ubuntu1.25\n')
        self.wheels = self.root / 'wheels'
        self.wheels.mkdir()
        self.dependency = self.wheels / 'example-1.0-py3-none-any.whl'
        with zipfile.ZipFile(self.dependency, 'w') as z:
            z.writestr('example-1.0.dist-info/METADATA', 'Name: example\nVersion: 1.0\n')
        digest = hashlib.sha256(self.dependency.read_bytes()).hexdigest()
        (self.script / 'runtime-requirements.lock').write_text(f'example==1.0 --hash=sha256:{digest}\n')
        self.wheel = self.root / 'client.whl'
        with zipfile.ZipFile(self.wheel, 'w') as z:
            z.writestr('aimee_vllm/__init__.py', '# registration only')
            z.writestr('aimee_vllm/client.so', b'compiled fixture')
        self.bank = self.root / 'kernels'
        self.bank.mkdir()
        (self.bank / 'kernel.hsaco').write_bytes(b'kernel fixture')
        (self.bank / 'manifest.json').write_text(json.dumps({'kernels':[{'files':['kernel.hsaco']}]}))
        self.library = self.root / 'runtime.so'
        self.library.write_bytes(b'compiled fixture')
        self.output = self.root / 'output'

    def run_builder(self):
        return subprocess.run([sys.executable, str(self.script/'context.py'), '--wheel', str(self.wheel),
            '--library', str(self.library), '--kernels', str(self.bank), '--runtime-wheels', str(self.wheels),
            '--output', str(self.output)], capture_output=True, text=True)

    def test_complete_locked_set_is_copied(self):
        result = self.run_builder()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.output/'os-packages.lock').read_bytes(), (self.script/'os-packages.lock').read_bytes())
        self.assertIn('runtime-wheels/'+self.dependency.name, json.loads(result.stdout)['artifact_digests'])

    def test_missing_extra_or_changed_wheel_rejected_before_output(self):
        original = self.dependency.read_bytes()
        self.dependency.unlink()
        self.assertNotEqual(self.run_builder().returncode, 0)
        self.dependency.write_bytes(original)
        extra = self.wheels/'extra.whl'
        extra.write_bytes(original)
        self.assertNotEqual(self.run_builder().returncode, 0)
        extra.unlink()
        with zipfile.ZipFile(self.dependency, 'a') as z:
            z.writestr('example/substitution.py', '# must not be trusted')
        self.assertNotEqual(self.run_builder().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_shell_text_in_os_lock_rejected(self):
        (self.script/'os-packages.lock').write_text('openssl=1;touch /tmp/not-permitted\n')
        self.assertNotEqual(self.run_builder().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_private_source_rejected(self):
        with zipfile.ZipFile(self.wheel, 'a') as z:
            z.writestr('aimee_vllm/private.py', '# private')
        self.assertNotEqual(self.run_builder().returncode, 0)
        self.assertFalse(self.output.exists())

if __name__ == '__main__':
    unittest.main()
