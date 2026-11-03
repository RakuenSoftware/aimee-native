"""A dependency notice scan must remain inside its public crate directory."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class NoticeBoundaryTests(unittest.TestCase):
    def test_symlinked_license_files_cannot_read_outside_the_crate(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            crate = work / 'crate'
            (crate / 'LICENSES').mkdir(parents=True)
            (crate / 'LICENSE').write_text('Public MIT notice fixture\n')
            outside = work / 'operator-file'
            outside.write_text('Private boundary fixture; must not be collected\n')
            (crate / 'LICENSE-escape').symlink_to(outside)
            (crate / 'LICENSES' / 'native.txt').symlink_to(outside)
            package = {'id': 'fixture', 'name': 'fixture', 'version': '1.0.0',
                'source': 'registry+https://github.com/rust-lang/crates.io-index',
                'manifest_path': str(crate / 'Cargo.toml'), 'license': 'MIT'}
            metadata = work / 'metadata.json'
            metadata.write_text(json.dumps({'resolve': {'root': 'fixture',
                'nodes': [{'id': 'fixture', 'deps': []}]}, 'packages': [package]}))
            notice, report = work / 'notices.txt', work / 'report.json'
            subprocess.run([sys.executable, str(Path(__file__).with_name('rust_licenses.py')),
                str(metadata), '--notice', str(notice), '--report', str(report)], check=True)
            self.assertIn('Public MIT notice fixture', notice.read_text())
            self.assertNotIn('Private boundary fixture', notice.read_text())
            self.assertEqual(json.loads(report.read_text())['packages'][0]['notice_files'], ['LICENSE'])


if __name__ == '__main__':
    unittest.main()
