"""Release identity must control the host-side memory position policy."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.native_addressing.legacy_cpu_preparation import local_compile


class LocalCompilerPositionPolicy(unittest.TestCase):
    def test_qwen_uses_request_policy_in_bounded_compiler(self):
        with tempfile.TemporaryDirectory() as directory:
            gguf = Path(directory) / 'model.gguf'
            gguf.write_bytes(b'fixture')
            request = {'identity': {'position_policy': 'negative'},
                       'response': {'facts': []}}
            argv = ['local_compile', '--model', directory, '--gguf', str(gguf),
                    '--output', str(Path(directory) / 'bank'), '--identity', 'model',
                    '--key', 'key']
            with (patch.object(sys, 'argv', argv),
                  patch.object(sys, 'stdin', io.StringIO(json.dumps(request))),
                  patch.object(local_compile.AutoConfig, 'from_pretrained') as config,
                  patch.object(local_compile, 'BoundedTextCompiler') as compiler):
                config.return_value.model_type = 'qwen3_5'
                local_compile.main()
            self.assertEqual(compiler.call_args.kwargs['memory_positions'], 'negative')
            compiler.return_value.compile.assert_called_once_with(
                request, str(Path(directory) / 'bank'), 'model', 'key')

    def test_rejects_nonnegative_release_identity(self):
        argv = ['local_compile', '--model', '.', '--output', 'bank',
                '--identity', 'model', '--key', 'key']
        with patch.object(sys, 'argv', argv), \
                patch.object(sys, 'stdin', io.StringIO(
                    json.dumps({'identity': {'position_policy': 'nonnegative'}}))):
            with self.assertRaisesRegex(ValueError, 'negative memory positions'):
                local_compile.main()


if __name__ == '__main__':
    unittest.main()
