"""Generate thin plugin bindings around one shared vLLM bridge."""
from pathlib import Path

COMMON_MODULES = (
    'preparation', 'runtime_ops', 'control', 'stream_completion', 'selection',
    'gguf_loader', 'admission', 'backend', 'binary_kernel', 'cache',
    'cache_identity', 'cli', 'state', 'store', 'worker', 'compatibility',
    'precision', 'telemetry', 'model_adapter', 'capture_session', 'hybrid',
    'capture', 'attention_capture',
)
PUBLIC_MODULES = ('kernel', 'decoder_kernel')

BINDING_SOURCE = '''"""Resolve the one installed plugin selected for this process."""
import hashlib
import json
import os
from pathlib import Path


def selected_binding():
    return load_binding(os.environ['AIMEE_NATIVE_PLUGIN_CONTRACT'])


def load_binding(contract):
    path = Path(contract).resolve(strict=True)
    binding = json.loads(path.read_bytes())
    library = path.parent / 'libaimee_native.so'
    if hashlib.sha256(library.read_bytes()).hexdigest() != binding['library_sha256']:
        raise RuntimeError('native library does not match its plugin binding')
    binding['library'] = str(library)
    binding['contract'] = str(path)
    return binding
'''


def shared_source(origin: Path, module: str) -> str:
    body = (origin / (module + '.py')).read_text().replace('aimee_vllm', 'aimee_native_runtime')
    if module == 'compatibility':
        body = body.replace("if not (Version('0.30.0') <= v < Version('0.31')):", "if v != Version('0.30.0'):").replace('supports the vLLM 0.30.x plugin interface', 'release requires the validated vLLM 0.30.0 interface')
    if module == 'model_adapter':
        body = body.replace('def __init__(self, config, library=None):', 'def __init__(self, config, library=None, binding=None):')
        body = body.replace('        from ._model import BOUND_ADAPTER',
                            '        from ._model import selected_binding\n        binding = binding or selected_binding()\n        BOUND_ADAPTER = binding["adapter"]')
        start = body.index('        # This is an entry-point registry')
        end = body.index('        self.serving = config', start)
        body = body[:start] + '''        symbol = binding['adapter_symbol']
        config.setdefault('library', binding['library'])
        import hashlib
        if hashlib.sha256(Path(config['library']).read_bytes()).hexdigest() != binding['library_sha256']:
            raise RuntimeError('serving library differs from installed model adapter')
''' + body[end:]
    if module == 'cli':
        body = body.replace("    if len(sys.argv)>1 and sys.argv[1] in ('connect-aimee','serve'):",
                            "    arguments = sys.argv[1:]\n    if arguments[:1] == ['--root']:\n        arguments = arguments[2:]\n    if arguments[:1] and arguments[0] in ('connect-aimee','serve'):")
        body = body.replace('    from ._model import BOUND_ADAPTER, PLUGIN_NAME',
                            '    from ._model import selected_binding\n    binding = selected_binding()\n    BOUND_ADAPTER, PLUGIN_NAME = binding["adapter"], binding["python_module"]')
        body = body.replace('        from ._model import BOUND_ADAPTER',
                            '        from ._model import selected_binding\n        binding = selected_binding()\n        BOUND_ADAPTER = binding["adapter"]')
        body = body.replace('    from ._model import BOUND_ADAPTER',
                            '    from ._model import selected_binding\n    binding = selected_binding()\n    BOUND_ADAPTER = binding["adapter"]')
        body = body.replace('str(Path(__file__).parent / "native/libaimee_native.so")', 'binding["library"]')
        body = body.replace("str(Path(__file__).parent/'native/adapter.json')", "binding['contract']")
        body = body.replace('if config.get("adapter") not in ("gemma4-12b", "gemma4-26b", "qwen3-8-27b"):',
                            'if config.get("adapter") != BOUND_ADAPTER:')
    return body


def write_binding(package: Path):
    package.mkdir(exist_ok=True)
    (package / 'cli.py').write_text('''"""Bind this plugin, then delegate to the shared serving CLI."""
import os
from pathlib import Path


def _bind():
    os.environ['AIMEE_NATIVE_PLUGIN_CONTRACT'] = str(Path(__file__).parent / 'native/adapter.json')


def command(config_path):
    _bind()
    from aimee_native_runtime.cli import command as shared_command
    return shared_command(config_path)


def main():
    _bind()
    from aimee_native_runtime.cli import main as shared_main
    shared_main()
''')
    (package / 'model_adapter.py').write_text('''"""This plugin's dedicated adapter through the shared ABI bridge."""
from pathlib import Path
from aimee_native_runtime._model import load_binding
from aimee_native_runtime.model_adapter import ModelAdapter as SharedAdapter


class ModelAdapter(SharedAdapter):
    def __init__(self, config, library=None):
        super().__init__(config, library, binding=load_binding(Path(__file__).parent / 'native/adapter.json'))
''')
    for name in (*COMMON_MODULES, *PUBLIC_MODULES):
        if name in ('cli', 'model_adapter'):
            continue
        (package / (name + '.py')).write_text(
            '"""Compatibility import for the shared runtime bridge."""\n'
            'import importlib, sys\n'
            f'sys.modules[__name__] = importlib.import_module("aimee_native_runtime.{name}")\n')
