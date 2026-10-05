"""Co-installed bindings must keep independent identities on one shared bridge."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from model_plugin_layout import BINDING_SOURCE, shared_source, write_binding

ORIGIN = Path(__file__).resolve().parents[1] / 'vllm/aimee_vllm'


class SharedLayoutTests(unittest.TestCase):
    def test_coinstalled_bindings_reject_each_others_models(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'aimee_native_runtime'
            runtime.mkdir()
            (runtime / '__init__.py').write_text('')
            (runtime / '_model.py').write_text(BINDING_SOURCE)
            (runtime / 'model_adapter.py').write_text(shared_source(ORIGIN, 'model_adapter'))
            (runtime / 'cli.py').write_text("from ._model import selected_binding\ndef command(path): return path, selected_binding()['adapter']\n")
            for model, package in [('gemma4-12b', 'aimee_gemma4_12b'), ('qwen3-8-27b', 'aimee_qwen3_8_27b')]:
                plugin = root / package
                write_binding(plugin)
                (plugin / '__init__.py').write_text('')
                (plugin / 'native').mkdir()
                data = model.encode()
                (plugin / 'native/libaimee_native.so').write_bytes(data)
                (plugin / 'native/adapter.json').write_text(json.dumps({
                    'adapter': model, 'adapter_symbol': package + '_adapter',
                    'python_module': package, 'library_sha256': hashlib.sha256(data).hexdigest()}))
            code = '''
import os
from pathlib import Path
from aimee_gemma4_12b.model_adapter import ModelAdapter as Gemma
from aimee_qwen3_8_27b.model_adapter import ModelAdapter as Qwen
from aimee_native_runtime.model_adapter import ModelAdapter as Shared
assert issubclass(Gemma, Shared) and issubclass(Qwen, Shared)
from aimee_gemma4_12b.cli import command as gemma_command
from aimee_qwen3_8_27b.cli import command as qwen_command
assert gemma_command('gemma-config') == ('gemma-config', 'gemma4-12b')
assert qwen_command('qwen-config') == ('qwen-config', 'qwen3-8-27b')
assert gemma_command('again') == ('again', 'gemma4-12b')
os.environ['AIMEE_NATIVE_PLUGIN_CONTRACT'] = str(Path('aimee_qwen3_8_27b/native/adapter.json').resolve())
for adapter, foreign in [(Gemma, 'qwen3-8-27b'), (Qwen, 'gemma4-12b')]:
    try:
        adapter({'adapter': foreign})
    except RuntimeError as error:
        assert 'different model' in str(error)
    else:
        raise AssertionError('cross-model binding accepted')
# Switching the process selection cannot change the explicitly bound plugin.
Path('aimee_gemma4_12b/native/libaimee_native.so').write_bytes(b'tampered')
try:
    Gemma({'adapter': 'gemma4-12b'})
except RuntimeError as error:
    assert 'does not match' in str(error)
else:
    raise AssertionError('tampered dedicated library accepted')
'''
            subprocess.run([sys.executable, '-c', code], cwd=root, check=True)


if __name__ == '__main__':
    unittest.main()
