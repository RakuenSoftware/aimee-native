import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import torch
from aimee_vllm.capture import PrefixCapture
from aimee_vllm.hybrid import HybridPrefix,validate_model_identity


class CaptureTests(unittest.TestCase):
    def _round_trip(self, gguf=False):
        with tempfile.TemporaryDirectory() as directory,patch('importlib.metadata.version',return_value='test'),patch('torch.cuda.get_device_capability',return_value=(11,0)):
            root=Path(directory);model=root/'model';model.mkdir()
            c={'quantization_config':{'quant_method':'fp8','activation_scheme':'dynamic'},'layer_types':['full_attention','linear_attention'],'num_key_value_heads':2,'head_dim':3,
               'linear_num_key_heads':2,'linear_num_value_heads':4,'linear_key_head_dim':2,
               'linear_value_head_dim':3,'linear_conv_kernel_dim':4}
            if gguf:c.pop('quantization_config')
            (model/'config.json').write_text(json.dumps(c));(model/'tokenizer.json').write_bytes(b'tokenizer')
            capture=PrefixCapture.__new__(PrefixCapture)
            capture.config={'model':str(model),'model_revision':'a'*40,'quantization':'fp8'}
            if gguf:capture.config.update(quantization=None,gguf_weights='/checkpoint.gguf',gguf_weights_sha256='a'*64,gguf_weight_profile='Q4_K_M')
            capture.architecture=c;capture.tokens=[11,12,13,14,15];capture.context='system'
            capture.destination=root/'output';capture.attention={};capture.recurrent={}
            keys=torch.arange(30,dtype=torch.bfloat16).reshape(5,2,3);values=keys+100
            for begin,end in [(0,2),(2,5)]:
                capture.attention_chunk(0,keys[begin:end],values[begin:end],NS(query_start_loc=torch.tensor([0,end-begin])))
            conv=torch.arange(80,dtype=torch.bfloat16).reshape(1,20,4)
            rnn=torch.arange(24,dtype=torch.float32).reshape(1,4,2,3)
            capture.recurrent={1:(conv,rnn)}
            result=capture.finish();out=capture.destination
            index=json.loads((out/'index.json').read_text());data=(out/'compact.pack').read_bytes()[4096:4096+index['dictionary_bytes']]
            expected=b''.join(x.transpose(0,1).contiguous().view(torch.uint8).numpy().tobytes() for x in (keys,values))
            self.assertEqual(data,expected)
            prefix=HybridPrefix(out,result['hybrid_state'],result['model'],result['key'])
            self.assertTrue(prefix.parts[1,'conv'].equal(conv));self.assertTrue(prefix.parts[1,'recurrent'].equal(rnn))
            validate_model_identity(prefix.spec,model,'a'*40,capture.config)
            with self.assertRaisesRegex(RuntimeError,'profile'):validate_model_identity(prefix.spec,model,'a'*40,{})

    def test_fp8_states_round_trip_exactly(self):
        self._round_trip()

    def test_q4_states_round_trip_exactly(self):
        self._round_trip(gguf=True)

    def test_incomplete_layers_and_capture_past_boundary_are_rejected(self):
        capture=PrefixCapture.__new__(PrefixCapture);capture.tokens=[1];capture.attention={};capture.recurrent={}
        capture.architecture={'layer_types':['full_attention','linear_attention']}
        with self.assertRaisesRegex(RuntimeError,'coverage'):capture.finish()
        with self.assertRaisesRegex(RuntimeError,'boundary'):
            capture.attention_chunk(0,torch.zeros(2,1,1,dtype=torch.bfloat16),torch.zeros(2,1,1,dtype=torch.bfloat16),NS(query_start_loc=torch.tensor([0,2])))

    def test_prompt_mismatch_or_batch_is_rejected_before_model_execution(self):
        capture=PrefixCapture.__new__(PrefixCapture);capture.tokens=[1,2];capture.request=None
        scheduler=NS(scheduled_new_reqs=[NS(req_id='r',prompt_token_ids=[1,3])],num_scheduled_tokens={'r':2},finished_req_ids=set())
        with self.assertRaisesRegex(RuntimeError,'identity'):capture.begin(scheduler)
        scheduler.scheduled_new_reqs=[NS(req_id='r',prompt_token_ids=[1,2])]
        capture.request='r'
        capture.begin(NS(scheduled_new_reqs=[],num_scheduled_tokens={},finished_req_ids={'r'}))
        capture.request=None
        scheduler.num_scheduled_tokens={'r':2,'other':2}
        with self.assertRaisesRegex(RuntimeError,'uninterrupted'):capture.begin(scheduler)

if __name__=='__main__':unittest.main()
