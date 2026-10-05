"""Release metadata must be visible to installers without changing tested code."""
import importlib.util
import base64
import csv
import hashlib
import io
from email.parser import BytesParser
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('finalizer', Path(__file__).with_name('finalize-model-plugins.py'))
finalizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finalizer)


class FinalizationTests(unittest.TestCase):
    def test_installer_sees_extra_for_metadata_without_body_separator(self):
        self.check_metadata(b'\n')

    def test_installer_sees_extra_for_metadata_with_body_separator(self):
        self.check_metadata(b'\n\n')

    def test_dependency_notices_are_recorded_without_changing_executables(self):
        self.check_metadata(b'\n\n', include_notices=True)

    def check_metadata(self, ending, include_notices=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheels = root / 'wheels'
            wheels.mkdir()
            dependency = root / 'vllm_gguf_plugin-0.0.5+triton-py3-none-any.whl'
            with zipfile.ZipFile(dependency, 'w') as archive:
                archive.writestr('vllm_gguf_plugin-0.0.5+triton.dist-info/METADATA', b'Version: 0.0.5+triton\n')
            packages = ('aimee_gemma4_12b', 'aimee_gemma4_26b', 'aimee_qwen3_8_27b', 'aimee_native_runtime')
            for package in packages:
                with zipfile.ZipFile(wheels / (package + '-0.3.0-cp312-cp312-linux_x86_64.whl'), 'w') as archive:
                    archive.writestr(package + '-0.3.0.dist-info/METADATA',
                        ('Metadata-Version: 2.4\nName: ' + package + '\nVersion: 0.3.0').encode() + ending)
                    archive.writestr(package + '/native/libaimee_native.so', b'previously-tested-executable')
                    if package == 'aimee_native_runtime':
                        executable = zipfile.ZipInfo(package + '/native/aimee-model-client')
                        executable.create_system = 3
                        executable.external_attr = 0o100755 << 16
                        archive.writestr(executable, b'previously-tested-client')
            output = root / 'release'
            notices = None
            if include_notices:
                notices = root / 'notices'
                notices.mkdir()
                for name in ('SHARED_CLIENT_NOTICES.txt', 'CYTHON_COPYING.txt', 'CYTHON_LICENSE.txt', 'THIRD_PARTY_NOTICES.txt'):
                    (notices / name).write_text('Public dependency notice: ' + name)
            finalizer.finalize(wheels, dependency, output, notices=notices)
            for package in packages:
                wheel = next(output.glob(package + '-*.whl'))
                with zipfile.ZipFile(wheel) as archive:
                    metadata = BytesParser().parsebytes(archive.read(package + '-0.3.0.dist-info/METADATA'))
                    self.assertEqual(archive.read(package + '/native/libaimee_native.so'), b'previously-tested-executable')
                    if package == 'aimee_native_runtime':
                        self.assertEqual(archive.getinfo(package + '/native/aimee-model-client').external_attr >> 16, 0o100755)
                    if 'gemma' in package:
                        self.assertEqual(metadata.get_all('Provides-Extra'), ['gguf'])
                        self.assertIn('vllm-gguf-plugin==0.0.5+triton; extra == "gguf"', metadata.get_all('Requires-Dist'))
                    else:
                        self.assertIsNone(metadata.get_all('Provides-Extra'))
                    if include_notices:
                        members = [name for name in archive.namelist() if '.dist-info/licenses/' in name]
                        self.assertEqual(len(members), 3 if package == 'aimee_native_runtime' else 1)
                        record = dict((row[0], row[1:]) for row in csv.reader(io.StringIO(archive.read(package + '-0.3.0.dist-info/RECORD').decode())))
                        for name in members:
                            data = archive.read(name)
                            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
                            self.assertEqual(record[name], ['sha256=' + digest, str(len(data))])
            self.assertEqual((output / dependency.name).read_bytes(), dependency.read_bytes())


if __name__ == '__main__':
    unittest.main()
