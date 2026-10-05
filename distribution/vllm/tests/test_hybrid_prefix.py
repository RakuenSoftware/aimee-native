import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest

import torch
from aimee_vllm.hybrid import HybridPrefix, seed_layer, validate_model_identity


class HybridPrefixTests(unittest.TestCase):
    def test_same_architecture_with_changed_revision_or_tokenizer_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'config.json').write_bytes(b'{}')
            (root/'tokenizer.json').write_bytes(b'tokenizer')
            revision='a'*40
            spec={'model_revision':revision,'model':hashlib.sha256(b'aimee-complete-hybrid-v1'+revision.encode()+b'\0{}tokenizer').hexdigest(),
                  'model_config_sha256':hashlib.sha256(b'{}').hexdigest(),
                  'tokenizer_sha256':hashlib.sha256(b'tokenizer').hexdigest(),'encoder_weight_profile':'bf16'}
            validate_model_identity(spec,root,revision)
            for changed in (None,'b'*40):
                with self.assertRaises(RuntimeError):validate_model_identity(spec,root,changed)
            (root/'tokenizer.json').write_bytes(b'new tokenizer')
            with self.assertRaises(RuntimeError):validate_model_identity(spec,root,revision)

    def test_conv_precision_mismatch_is_rejected_before_cache_write(self):
        conv=torch.arange(60,dtype=torch.float32).reshape(20,3)/7
        recurrent=torch.arange(24,dtype=torch.float32).reshape(4,3,2)
        hybrid=NS(devices={('cpu',0,1):{0:(conv,recurrent)}})
        module=NS(kv_cache=(torch.zeros(2,20,3,dtype=torch.bfloat16),torch.zeros(2,4,3,2)))
        runner=NS(input_batch=NS(req_ids=['native'],num_computed_tokens_cpu=[0]))
        requests={'native':NS(store=NS(hybrid=hybrid))}
        metadata=NS(non_spec_state_indices_tensor=torch.tensor([1]),spec_sequence_masks=None,
                    has_initial_state=torch.tensor([False]),prefill_has_initial_state=torch.tensor([False]),num_decodes=0)
        with self.assertRaisesRegex(RuntimeError,'geometry/dtype'):
            seed_layer(module,0,runner,requests,0,1,metadata,True,NS(call=lambda *a,**k:[i for i,(memory,computed,slot) in enumerate(k['requests']) if memory and computed==0]))
        self.assertTrue(all(t.eq(0).all() for t in module.kv_cache))
        self.assertEqual(metadata.has_initial_state.tolist(),[False])

    def test_decode_and_plain_requests_never_copy_physical_slots_to_host(self):
        class Slots:
            shape=(1,)
            def tolist(self):raise AssertionError('unnecessary device synchronization')
        metadata=NS(non_spec_state_indices_tensor=Slots(),spec_sequence_masks=None)
        for store,computed in [(None,0),(NS(hybrid=object()),7)]:
            runner=NS(input_batch=NS(req_ids=['request'],num_computed_tokens_cpu=[computed]))
            self.assertEqual(seed_layer(NS(),0,runner,{'request':NS(store=store)},0,1,metadata,True,NS(call=lambda *a,**k:[i for i,(memory,computed,slot) in enumerate(k['requests']) if memory and computed==0])),0)
        with self.assertRaisesRegex(RuntimeError,'not pinned'):
            seed_layer(NS(),0,runner,{},0,1,metadata,True,NS(call=lambda *a,**k:[i for i,(memory,computed,slot) in enumerate(k['requests']) if memory and computed==0]))

    def test_matching_bf16_conv_seed_is_copied_without_conversion(self):
        conv=torch.arange(60,dtype=torch.bfloat16).reshape(20,3)
        recurrent=torch.arange(24,dtype=torch.float32).reshape(4,3,2)
        hybrid=NS(devices={('cpu',0,1):{0:(conv,recurrent)}})
        module=NS(kv_cache=(torch.zeros(2,20,3,dtype=torch.bfloat16),torch.zeros(2,4,3,2)))
        runner=NS(input_batch=NS(req_ids=['native'],num_computed_tokens_cpu=[0]))
        metadata=NS(non_spec_state_indices_tensor=torch.tensor([1]),spec_sequence_masks=None,
                    has_initial_state=torch.tensor([False]),prefill_has_initial_state=torch.tensor([False]),num_decodes=0)
        self.assertEqual(seed_layer(module,0,runner,{'native':NS(store=NS(hybrid=hybrid))},0,1,metadata,True,NS(call=lambda *a,**k:[i for i,(memory,computed,slot) in enumerate(k['requests']) if memory and computed==0])),1)
        self.assertTrue(module.kv_cache[0][1].equal(conv))
        self.assertTrue(module.kv_cache[1][1].equal(recurrent))
        module.kv_cache[0][1].add_(1)
        self.assertFalse(module.kv_cache[0][1].equal(conv))

    def fixture(self, root):
        c={'linear_num_key_heads':2,'linear_num_value_heads':4,
           'linear_key_head_dim':2,'linear_value_head_dim':3,
           'linear_conv_kernel_dim':4,'layer_types':['linear_attention','full_attention']}
        conv=torch.arange(80,dtype=torch.float32).reshape(1,20,4)
        recurrent=torch.arange(24,dtype=torch.float32).reshape(1,4,2,3)
        data=conv.numpy().tobytes()+recurrent.numpy().tobytes()
        digest=hashlib.sha256(data).hexdigest();payload=digest+'.rnn.bin'
        (root/payload).write_bytes(data);(root/'index.json').write_text('{}')
        layouts=[];offset=0
        for part,t in [('conv',conv),('recurrent',recurrent)]:
            n=t.numel()*t.element_size()
            layouts.append({'layer':0,'part':part,'dtype':'f32','shape':list(t.shape),'offset':offset,'bytes':n});offset+=n
        spec={'schema':1,'model':'model','key':'key','architecture':c,'positioning':'native-prefix-absolute-v1',
              'attention_index_sha256':hashlib.sha256(b'{}').hexdigest(),
              'recurrent':{'version':1,'bytes':len(data),'sha256':digest,'payload':payload,'layouts':layouts}}
        raw=json.dumps(spec).encode();(root/'hybrid.json').write_bytes(raw)
        return hashlib.sha256(raw).hexdigest(),conv,recurrent,spec

    def test_partition_slices_each_qkv_group_and_transposes_recurrence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);digest,conv,recurrent,_=self.fixture(root)
            prefix=HybridPrefix(root,digest,'model','key')
            for rank in range(2):
                got,state=prefix.partition(rank,2)[0]
                expected=torch.cat([t[rank*(t.shape[0]//2):(rank+1)*(t.shape[0]//2),-3:]
                                    for t in conv[0].split([4,4,12])])
                self.assertTrue(got.equal(expected))
                self.assertTrue(state.equal(recurrent[0,rank*2:(rank+1)*2].transpose(-1,-2)))
            self.assertEqual(prefix.device_bytes(0,2),168)
            with self.assertRaisesRegex(RuntimeError,'partition'):prefix.partition(0,3)

    def test_payload_integrity_budget_and_manifest_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);digest,_,_,spec=self.fixture(root)
            with self.assertRaisesRegex(RuntimeError,'budget'):HybridPrefix(root,digest,'model','key',limit=1)
            with self.assertRaisesRegex(RuntimeError,'publication'):HybridPrefix(root,digest,'wrong','key')
            payload=root/spec['recurrent']['payload'];raw=bytearray(payload.read_bytes());raw[0]^=1;payload.write_bytes(raw)
            with self.assertRaisesRegex(RuntimeError,'checksum'):HybridPrefix(root,digest,'model','key')

    def test_positions_shift_before_rotary_for_only_the_selected_requests(self):
        positions=torch.tensor([[0,1,2,10,11,0],[0,1,2,10,11,0],[0,1,2,10,11,0]])
        original=positions.clone()
        requests={'native':NS(store=NS(hybrid=object(),metadata={'positions':67})),
                  'plain':NS(store=None)}
        metadata=NS(aimee_ids=['plain','native'],query_start_loc=torch.tensor([0,3,5]))
        import os
        if not os.environ.get('AIMEE_STORE_LIBRARY'):
            self.skipTest('requires the real Rust model adapter')
        from aimee_vllm.model_adapter import ModelAdapter
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        model=Path(temporary.name)
        (model/'config.json').write_bytes((Path(__file__).parent/'model_configs/qwen3-8-27b.json').read_bytes())
        adapter=ModelAdapter({'model':str(model),'adapter':'qwen3-8-27b','library':os.environ['AIMEE_STORE_LIBRARY']})
        positioned_arguments=adapter.positioned_arguments
        args,kwargs=positioned_arguments((None,positions),{},requests,metadata)
        self.assertTrue(args[1].equal(original+torch.tensor([0,0,0,67,67,0])))
        self.assertTrue(positions.equal(original))
        _,kwargs=positioned_arguments((),{'positions':positions[0]},requests,metadata)
        self.assertTrue(kwargs['positions'].equal(args[1][0]))
        metadata.aimee_ids=['missing','native']
        with self.assertRaisesRegex(RuntimeError,'not pinned'):
            positioned_arguments((None,positions),{},requests,metadata)

    def test_reordered_mixed_requests_decode_and_preemption_keep_private_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);digest,_,_,_=self.fixture(root)
            prefix=HybridPrefix(root,digest,'model','key');prefix.activate('cpu',0,1)
            module=NS(kv_cache=(torch.zeros(5,20,3),torch.zeros(5,4,3,2)))
            runner=NS(input_batch=NS(req_ids=['plain','native'],num_computed_tokens_cpu=[0,0]))
            requests={'plain':NS(store=None),'native':NS(store=NS(hybrid=prefix))}
            metadata=NS(non_spec_state_indices_tensor=torch.tensor([3,1]),spec_sequence_masks=None,
                        has_initial_state=torch.tensor([False,False]),prefill_has_initial_state=torch.tensor([False,False]),num_decodes=0)
            original=tuple(t.clone() for t in prefix.devices['cpu',0,1][0])
            seed_layer(module,0,runner,requests,0,1,metadata,True,NS(call=lambda *a,**k:[i for i,(memory,computed,slot) in enumerate(k['requests']) if memory and computed==0]))
            self.assertTrue(module.kv_cache[0][3].eq(0).all())
            self.assertTrue(module.kv_cache[0][1].equal(original[0]))
            self.assertEqual(metadata.has_initial_state.tolist(),[False,True])
            module.kv_cache[1][1].add_(9)
            runner.input_batch.num_computed_tokens_cpu=[0,5]
            seed_layer(module,0,runner,requests,0,1,metadata,True,NS(call=lambda *a,**k:[i for i,(memory,computed,slot) in enumerate(k['requests']) if memory and computed==0]))
            self.assertTrue(module.kv_cache[1][1].equal(original[1]+9))
            runner.input_batch.req_ids=['native','plain'];runner.input_batch.num_computed_tokens_cpu=[0,0]
            metadata.non_spec_state_indices_tensor=torch.tensor([4,2])
            seed_layer(module,0,runner,requests,0,1,metadata,True,NS(call=lambda *a,**k:[i for i,(memory,computed,slot) in enumerate(k['requests']) if memory and computed==0]))
            self.assertTrue(module.kv_cache[1][4].equal(original[1]))
            self.assertTrue(prefix.devices['cpu',0,1][0][1].equal(original[1]))
            requests.pop('native')
            with self.assertRaisesRegex(RuntimeError,'not pinned'):
                seed_layer(module,0,runner,requests,0,1,metadata,True,NS(call=lambda *a,**k:[i for i,(memory,computed,slot) in enumerate(k['requests']) if memory and computed==0]))


if __name__=='__main__':unittest.main()
