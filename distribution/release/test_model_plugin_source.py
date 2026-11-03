"""A source build must not copy an entire operator workspace into staging."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('model_plugin_builder',
    Path(__file__).with_name('build-model-plugins.py'))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class SourceStagingTests(unittest.TestCase):
    def test_code_only_staging_and_repository_toolchain_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, repo, staged = (root / name for name in ('snapshot', 'repo', 'staged'))
            for path in (source / 'native', repo / 'src', repo / 'native'):
                path.mkdir(parents=True)
            (source / 'Cargo.toml').write_text('[package]\nname="snapshot"\n')
            (source / 'Cargo.lock').write_text('version = 4\n')
            (source / 'native/compat.h').write_text('snapshot bridge')
            (source / 'model.safetensors').write_text('excluded model fixture')
            (source / '.env').write_text('excluded configuration fixture')
            (source / 'target').mkdir()
            (source / 'target/cache').write_text('excluded build fixture')
            (repo / 'rust-toolchain.toml').write_text('[toolchain]\nchannel="1.98.1"\n')
            (repo / 'src/lib.rs').write_text('// maintained adapter')
            (repo / 'build.rs').write_text('fn main() {}')
            (repo / 'native/vllm_runtime_portable.cpp').write_text('// maintained bridge')
            builder.stage_rust_source(source, repo, staged)
            self.assertEqual({p.name for p in staged.iterdir()},
                             {'Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml', 'native', 'src', 'build.rs'})
            self.assertEqual((staged / 'src/lib.rs').read_text(), '// maintained adapter')
            self.assertEqual((staged / 'native/compat.h').read_text(), 'snapshot bridge')
            self.assertEqual((staged / 'native/vllm_runtime_portable.cpp').read_text(), '// maintained bridge')
            self.assertEqual((staged / 'rust-toolchain.toml').read_bytes(),
                             (repo / 'rust-toolchain.toml').read_bytes())


if __name__ == '__main__':
    unittest.main()
