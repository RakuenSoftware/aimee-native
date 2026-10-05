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

    def test_unsupported_quantization_is_fail_closed(self):
        for config in ({'quantization':'int8'},{'quantization':'fp8','gguf_weights':'file'}):
            with self.assertRaises(ValueError):runtime_profile(config)

if __name__=='__main__':unittest.main()
