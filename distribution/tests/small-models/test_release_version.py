"""Run against an environment containing all five 0.3.3 candidate plugins."""
from importlib.metadata import version
import unittest
from unittest.mock import patch
from aimee_native_runtime import compatibility


class InstalledReleaseTests(unittest.TestCase):
    def test_release_versions(self):
        for name in ('aimee-native-runtime', 'aimee-gemma4-12b', 'aimee-gemma4-26b',
                     'aimee-qwen3-8-27b', 'aimee-gemma4-e2b', 'aimee-gemma4-e4b'):
            with self.subTest(package=name):
                self.assertEqual(version(name), '0.3.3')

    def test_compiled_runtime_interface(self):
        cases = [('0.30.0', True), ('0.30.0+rocm723', True), ('0.30.0+cuda', True),
                 ('0.30.1', False), ('0.31.0', False), ('0.30.0rc1', False),
                 ('0.30.0.post1', False), ('0.29.0', False)]
        for candidate, accepted in cases:
            with self.subTest(version=candidate), patch.object(compatibility, 'version', return_value=candidate):
                if accepted:
                    compatibility.check_interface()
                else:
                    with self.assertRaises(RuntimeError):
                        compatibility.check_interface()


if __name__ == '__main__':
    unittest.main()
