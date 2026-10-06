import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from aimee_vllm.precision import runtime_profile, model_identity
from aimee_vllm.hybrid import validate_model_identity


class PrecisionTests(unittest.TestCase):
    def test_old_identity_is_preserved_and_cross_precision_states_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch('importlib.metadata.version',return_value='test'):
            root=Path(directory);config=json.dumps({'quantization_config':{'quant_method':'fp8','activation_scheme':'dynamic'}}).encode();tokenizer=b'tokens';revision='a'*40
            (root/'config.json').write_bytes(config);(root/'tokenizer.json').write_bytes(tokenizer)
            profile=runtime_profile({'quantization':'fp8'})
            self.assertEqual(model_identity(config,tokenizer,revision,None),hashlib.sha256(b'aimee-complete-hybrid-v1'+revision.encode()+b'\0'+config+tokenizer).hexdigest())
            spec={'model_revision':revision,'model':model_identity(config,tokenizer,revision,profile),
                  'model_config_sha256':hashlib.sha256(config).hexdigest(),'tokenizer_sha256':hashlib.sha256(tokenizer).hexdigest(),
                  'encoder_weight_profile':'vllm-fp8','runtime_profile':profile}
            validate_model_identity(spec,root,revision,{'quantization':'fp8'})
            with self.assertRaisesRegex(RuntimeError,'profile'):validate_model_identity(spec,root,revision,{})
            with patch('importlib.metadata.version',return_value='changed'):
                with self.assertRaisesRegex(RuntimeError,'profile'):validate_model_identity(spec,root,revision,{'quantization':'fp8'})
            with self.assertRaisesRegex(RuntimeError,'profile'):
                validate_model_identity(spec,root,revision,{'quantization':'fp8','serve':{'gdn_prefill_backend':'flashinfer'}})

    def test_q4_identity_binds_checkpoint_runtime_and_gpu(self):
        base={'gguf_weights':'/checkpoint.gguf','gguf_weights_sha256':'a'*64,'gguf_weight_profile':'Q4_K_M'}
        with tempfile.TemporaryDirectory() as directory,patch('importlib.metadata.version',return_value='test'),patch('torch.cuda.get_device_capability',return_value=(11,0)):
            root=Path(directory);config=b'{}';tokenizer=b'tokens';revision='a'*40
            (root/'config.json').write_bytes(config);(root/'tokenizer.json').write_bytes(tokenizer)
            profile=runtime_profile(base)
            spec={'model_revision':revision,'model':model_identity(config,tokenizer,revision,profile),
                  'model_config_sha256':hashlib.sha256(config).hexdigest(),'tokenizer_sha256':hashlib.sha256(tokenizer).hexdigest(),
                  'encoder_weight_profile':'vllm-gguf-Q4_K_M','runtime_profile':profile}
            validate_model_identity(spec,root,revision,base)
            for changed in ({'gguf_weights_sha256':'b'*64},{'serve':{'gdn_prefill_backend':'flashinfer'}}):
                with self.subTest(changed=changed),self.assertRaisesRegex(RuntimeError,'profile'):
                    validate_model_identity(spec,root,revision,dict(base,**changed))
            with patch('torch.cuda.get_device_capability',return_value=(12,0)):
                with self.assertRaisesRegex(RuntimeError,'profile'):validate_model_identity(spec,root,revision,base)
            with patch('importlib.metadata.version',return_value='changed'):
                with self.assertRaisesRegex(RuntimeError,'profile'):validate_model_identity(spec,root,revision,base)
            with self.assertRaisesRegex(RuntimeError,'profile'):validate_model_identity(spec,root,revision,{})
            for changed in ({'gguf_weight_profile':'Q8_0'},{'gguf_weights_sha256':None},{'gguf_weights_sha256':'typo'},{'gguf_matrix_backend':'cuda'}):
                with self.subTest(changed=changed),self.assertRaises(ValueError):runtime_profile(dict(base,**changed))

    def test_unsupported_quantization_is_fail_closed(self):
        for config in ({'quantization':'int8'},{'quantization':'fp8','gguf_weights':'file'}):
            with self.assertRaises(ValueError):runtime_profile(config)

if __name__=='__main__':unittest.main()
