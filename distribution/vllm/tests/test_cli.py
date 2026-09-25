import json,pathlib,tempfile,unittest
from aimee_vllm.cli import command
class CliTests(unittest.TestCase):
    def test_gguf_uses_registered_loader_options_without_upstream_patching_entrypoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'serving.json'
            path.write_text(json.dumps({'model':'/models/gemma','library':'/lib/native.so','catalog':'/memory/catalog.json','recipient':'fixture','host_memory_budget':1024,'gguf_weights':'/models/gemma.gguf'}))
            args,env=command(path)
        self.assertNotIn('--model-weights',args)
        self.assertEqual(json.loads(args[args.index('--model-loader-extra-config')+1]),{'gguf_weights':'/models/gemma.gguf'})
        self.assertEqual(env['VLLM_PLUGINS'],'aimee_native')
        self.assertEqual(env['AIMEE_GGUF_ENABLE'],'1')
        self.assertEqual(args[args.index('--load-format')+1],'aimee_gguf_unified')
