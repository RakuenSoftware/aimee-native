"""Check release API pinning without rejecting validated vendor wheel suffixes."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'distribution/release'))
from model_plugin_layout import shared_source


class ReleaseInterfaceTests(unittest.TestCase):
    def test_public_version_pin(self):
        namespace = {}
        exec(shared_source(ROOT / 'distribution/vllm/aimee_vllm', 'compatibility'), namespace)
        cases = [('0.30.0', True), ('0.30.0+rocm723', True),
                 ('0.30.0+cuda', True), ('0.30.1', False),
                 ('0.31.0', False), ('0.30.0rc1', False),
                 ('0.30.0.post1', False), ('0.29.0', False)]
        for version, accepted in cases:
            with self.subTest(version=version), patch.dict(namespace, version=lambda _: version):
                if accepted:
                    namespace['check_interface']()
                else:
                    with self.assertRaises(RuntimeError):
                        namespace['check_interface']()


if __name__ == '__main__':
    unittest.main()
