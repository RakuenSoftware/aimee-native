"""Signed manifests must fail closed before any installer is invoked."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('release_bundle', Path(__file__).with_name('release-bundle.py'))
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class SignatureBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.key = self.root / 'key.pem'
        self.public = self.root / 'public.pem'
        self.other = self.root / 'other.pem'
        for path in (self.key, self.root / 'other-key.pem'):
            subprocess.run(['openssl', 'genpkey', '-algorithm', 'ED25519', '-out', str(path)], check=True)
        for private, public in ((self.key, self.public), (self.root / 'other-key.pem', self.other)):
            subprocess.run(['openssl', 'pkey', '-in', str(private), '-pubout', '-out', str(public)], check=True)
        self.payload = self.root / 'bundle'
        self.payload.mkdir()
        self.rows = []
        for i in range(7):
            p = self.payload / (str(i) + '.whl')
            p.write_bytes(b'qualified fixture bytes ' + bytes([i]))
            self.rows.append(dict(name=p.name, role='wheel', bytes=p.stat().st_size, sha256=bundle.digest(p)))
        self.sign()

    def sign(self):
        p = self.payload / 'manifest.json'
        p.write_text(json.dumps(dict(schema=1, repository=bundle.REPOSITORY, version='0.3.4', files=self.rows)))
        subprocess.run(['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(self.key),
                        '-in', str(p), '-out', str(self.payload / 'manifest.sig')], check=True)

    def test_correct_signature_version_and_bytes_pass(self):
        self.assertEqual(bundle.verify(self.payload, self.public, '0.3.4')['version'], '0.3.4')

    def test_tampered_payload_is_rejected(self):
        (self.payload / '0.whl').write_bytes(b'tampered fixture bytes')
        with self.assertRaisesRegex(ValueError, 'asset mismatch'):
            bundle.verify(self.payload, self.public, '0.3.4')

    def test_wrong_identity_and_changed_manifest_are_rejected(self):
        with self.assertRaises(subprocess.CalledProcessError):
            bundle.verify(self.payload, self.other, '0.3.4')
        with (self.payload / 'manifest.json').open('a') as f:
            f.write(' ')
        with self.assertRaises(subprocess.CalledProcessError):
            bundle.verify(self.payload, self.public, '0.3.4')

    def test_unlisted_wheel_and_downgrade_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unexpected release version'):
            bundle.verify(self.payload, self.public, '0.3.5')
        (self.payload / 'injected.whl').write_bytes(b'unlisted payload')
        with self.assertRaisesRegex(ValueError, 'unlisted assets'):
            bundle.verify(self.payload, self.public, '0.3.4')

    def test_even_a_signed_manifest_cannot_escape_its_directory(self):
        self.rows[0]['name'] = '../0.whl'
        self.sign()
        with self.assertRaisesRegex(ValueError, 'invalid or duplicate'):
            bundle.verify(self.payload, self.public, '0.3.4')

    def test_symlink_assets_are_rejected(self):
        p = self.payload / '0.whl'
        target = self.root / 'outside.whl'
        target.write_bytes(p.read_bytes())
        p.unlink()
        p.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'missing regular asset'):
            bundle.verify(self.payload, self.public, '0.3.4')


if __name__ == '__main__':
    unittest.main()
