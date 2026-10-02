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

    def test_memory_aware_prefix_and_async_flags_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'serving.json'
            base={'model':'/models/gemma','library':'/lib/native.so','catalog':'/memory/catalog.json',
                  'recipient':'fixture','host_memory_budget':1024}
            path.write_text(json.dumps(dict(base,serve={'enable_prefix_caching':True,'async_scheduling':True,'enable_model_compilation':True,'enable_piecewise_graphs':True})))
            args,env=command(path)
            self.assertIn('--enable-prefix-caching',args)
            self.assertIn('--async-scheduling',args)
            self.assertNotIn('--no-enable-prefix-caching',args)
            self.assertNotIn('--no-async-scheduling',args)
            self.assertNotIn('--enforce-eager',args)
            self.assertEqual(json.loads(args[args.index('--compilation-config')+1]),{'mode':3,'cudagraph_mode':'PIECEWISE'})
            self.assertEqual(env['VLLM_USE_V2_MODEL_RUNNER'],'0')
            for key in ('enable_prefix_caching','async_scheduling','enable_model_compilation','enable_piecewise_graphs','v2_model_runner'):
                path.write_text(json.dumps(dict(base,serve={key:'true'})))
                with self.assertRaisesRegex(ValueError,'must be a boolean'):
                    command(path)
            path.write_text(json.dumps(dict(base,serve={'enable_piecewise_graphs':True})))
            with self.assertRaisesRegex(ValueError,'require model compilation'):
                command(path)
            path.write_text(json.dumps(dict(base,serve={'v2_model_runner':True})))
            _,env=command(path)
            self.assertEqual(env['VLLM_USE_V2_MODEL_RUNNER'],'1')
