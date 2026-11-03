import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


source = load('source_archive', 'source-archive.py')
publisher = load('github_publisher', 'publish-github-release.py')


class DeliveryTests(unittest.TestCase):
    def test_export_is_immutable_repeatable_and_excludes_operator_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repo = root / 'repo'
            repo.mkdir()
            def git(*args):
                return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL)
            git('init', '-q')
            (repo / 'source.py').write_text('published source\n')
            (repo / 'run').write_text('executable fixture\n')
            (repo / 'run').chmod(0o755)
            (repo / 'link').symlink_to('source.py')
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '-qm', 'source fixture')
            revision = git('rev-parse', 'HEAD').decode().strip()
            (repo / 'source.py').write_text('uncommitted operator edit\n')
            (repo / 'operator.key').write_text('private fixture; exclude\n')
            first, second = root / 'first.zip', root / 'second.zip'
            source.archive(repo, revision, first, 'source/')
            source.archive(repo, revision, second, 'source/')
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.read('source/source.py'), b'published source\n')
                self.assertEqual(archive.read('source/link'), b'source.py')
                self.assertEqual(archive.getinfo('source/run').external_attr >> 16, 0o100755)
                self.assertEqual(set(archive.namelist()), {'source/source.py', 'source/run', 'source/link'})

    def test_retry_refuses_wrong_target_unknown_assets_and_wrong_bytes(self):
        expected = {'wheel.whl': {'bytes': 3, 'sha256': 'abc'}}
        valid = {'tag_name': 'v1', 'target_commitish': 'commit', 'assets': [
            {'name': 'wheel.whl', 'size': 3, 'digest': 'sha256:abc'}]}
        self.assertEqual(publisher.validate_metadata(valid, 'v1', 'commit', expected), {'wheel.whl'})
        for patch in ({'target_commitish': 'other'}, {'assets': [{'name': 'unexpected', 'size': 3}]},
                      {'assets': [{'name': 'wheel.whl', 'size': 4}]},
                      {'assets': [{'name': 'wheel.whl', 'size': 3, 'digest': 'sha256:wrong'}]}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                publisher.validate_metadata(dict(valid, **patch), 'v1', 'commit', expected)


if __name__ == '__main__':
    unittest.main()
