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
        self.assertEqual(env['VLLM_GGUF_USE_CUDA'],'0')
        self.assertEqual(args[args.index('--load-format')+1],'aimee_gguf_unified')

    def test_signed_larger_model_options_reach_upstream_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'serving.json'
            base={'model':'/models/qwen','library':'/lib/native.so','catalog':'/memory/catalog.json','recipient':'fixture','host_memory_budget':1024,'gguf_weights':'/models/qwen.gguf'}
            for backend,expected in [('cuda','1'),('triton','0')]:
                path.write_text(json.dumps(dict(base,gguf_matrix_backend=backend,mm_proj='/models/projector.gguf')))
                args,env=command(path)
                loader=json.loads(args[args.index('--model-loader-extra-config')+1])
                self.assertEqual(loader,{'gguf_weights':'/models/qwen.gguf','mm_proj':'/models/projector.gguf'})
                self.assertEqual(env['VLLM_GGUF_USE_CUDA'],expected)
            path.write_text(json.dumps(dict(base,gguf_matrix_backend='typo')))
            with self.assertRaisesRegex(ValueError,'unsupported GGUF'):
                command(path)
