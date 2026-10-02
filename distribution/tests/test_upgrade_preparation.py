"""Exercise deployment and rollback without services or model loading."""
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = pathlib.Path(__file__).with_name('upgrade_preparation.py')

class PreparationUpgrade(unittest.TestCase):
    def exercise(self, fail_revision=False):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            compiler, stage, config, report = [root / name for name in ('compiler', 'stage', 'config', 'report')]
            for p in (compiler, stage, config, report):p.mkdir()
            for name in ('gemma_compile.py','resident_compile.py'):
                (compiler/name).write_text('# old\n')
                (stage/name).write_text('# new\n')
            (compiler/'resident.json').write_text(json.dumps({'model':'unchanged'}))
            for name in ('worker.json','worker.oneshot.json'):
                (compiler/name).write_text(json.dumps({'compiler':['python','compiler.py'],'resident_socket':'unchanged'}))
            (config/'preparation.json').write_text(json.dumps({'encoding_revision':'native-negative-v1','authority':'unchanged'}))
            mappings = {'/opt/aimee-native-compiler':str(compiler),
                        '/opt/aimee-memory-lab/release-candidate-20260927/preparation':str(stage),
                        '/etc/aimee-native':str(config)}
            failed = False
            commands = []
            def output(argv, **kw):
                nonlocal failed
                if argv[2]=='113':return b'{"status":"complete"}'
                if 'journalctl' in argv:return '{"event": "ready"}\n'
                source=kw['input']
                if fail_revision and argv[2]=='100' and 'assert d[' in source and not failed:
                    failed=True
                    raise subprocess.CalledProcessError(1,argv)
                for old,new in mappings.items():source=source.replace(old,new)
                exec(compile(source,'isolated-remote','exec'),{})
                return ''
            def command(argv, **kw):commands.append(argv)
            source=SCRIPT.read_text().replace('/root/aimee-release-cert-20260927',str(report))
            with patch('subprocess.check_output',side_effect=output), patch('subprocess.run',side_effect=command):
                if fail_revision:
                    with self.assertRaises(subprocess.CalledProcessError):exec(compile(source,str(SCRIPT),'exec'),{})
                else:exec(compile(source,str(SCRIPT),'exec'),{})
            result=json.loads((report/'preparation-upgrade.json').read_text())
            resident=json.loads((compiler/'resident.json').read_text())
            prep=json.loads((config/'preparation.json').read_text())
            self.assertEqual(resident['model'],'unchanged');self.assertEqual(prep['authority'],'unchanged')
            if fail_revision:
                self.assertEqual(result['status'],'failed')
                self.assertNotIn('compute_dtype',resident)
                self.assertEqual(prep['encoding_revision'],'native-negative-v1')
                self.assertEqual((compiler/'gemma_compile.py').read_text(),'# old\n')
                self.assertIn('rollback',result)
            else:
                self.assertEqual(result['status'],'deployed_pending_client_validation')
                self.assertEqual(resident['compute_dtype'],'float32')
                self.assertEqual(prep['encoding_revision'],'native-negative-v2-fp32')
                for name in ('worker.json','worker.oneshot.json'):
                    self.assertEqual(json.loads((compiler/name).read_text())['compiler'][-2:],['--compute-dtype','float32'])
            self.assertTrue(commands)

    def test_upgrade_preserves_authority_and_changes_cache_revision(self):self.exercise()
    def test_failure_restores_original_compiler_and_revision(self):self.exercise(True)

if __name__=='__main__':unittest.main()
