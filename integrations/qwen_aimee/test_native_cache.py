import unittest
import torch
from test_adapter import tiny_model, Tokenizer
from qwen_adapter import QwenAimeeAdapter

class Client:
    def __init__(self):self.facts=[{'id':1,'content':'drink oolong'}];self.calls=0
    def search(self,q,k):self.calls+=1;return {'facts':self.facts,'windows':[]}

class NativeCacheTests(unittest.TestCase):
    def test_cache_reuses_states_only_after_authorized_recall(self):
        model=tiny_model();client=Client();adapter=QwenAimeeAdapter(model,Tokenizer(),client,host_memory=True,encoding_cache_bytes=1<<20)
        self.addCleanup(adapter.close);ids=torch.tensor([[1,7,11]])
        def run(reuse=True):
            with torch.inference_mode(),adapter.request('drink',reuse_encoding=reuse) as state:
                logits=model(input_ids=ids,use_cache=True).logits.clone()
                passes=state['memory_encoding_passes'];reads=state['native_reads']
            return logits,passes,reads
        first,n,_=run();self.assertEqual(n,1)
        second,n,_=run();self.assertEqual(n,0);self.assertTrue(torch.equal(first,second));self.assertEqual(client.calls,2)
        _,n,_=run(False);self.assertEqual(n,1)
        client.facts=[]
        _,n,reads=run();self.assertEqual(n,0);self.assertEqual(reads,0)
        client.facts=[{'id':1,'content':'changed memory content longer'}]
        _,n,_=run();self.assertEqual(n,1)
        self.assertLessEqual(adapter.encoding_cache_size,adapter.encoding_cache_budget)
    def test_native_states_are_partitioned_by_authorization(self):
        client=Client();client.authorization_id='grant-a'
        adapter=QwenAimeeAdapter(tiny_model(),Tokenizer(),client,host_memory=True,encoding_cache_bytes=1<<20)
        self.addCleanup(adapter.close)
        for identity,expected in [('grant-a',1),('grant-a',0),('grant-b',1),('grant-b',0)]:
            client.authorization_id=identity
            with torch.inference_mode(),adapter.request('drink') as state:
                adapter.model(input_ids=torch.tensor([[1,7,11]]),use_cache=True)
                self.assertEqual(state['memory_encoding_passes'],expected)

    def test_revoked_authorization_cannot_reactivate_cached_states(self):
        from aimee_client import AimeeError
        class Guarded(Client):
            authorization_id='grant-a'
            active=True
            def begin_request(self):
                if not self.active:raise AimeeError('revoked')
        client=Guarded()
        adapter=QwenAimeeAdapter(tiny_model(),Tokenizer(),client,host_memory=True,encoding_cache_bytes=1<<20)
        self.addCleanup(adapter.close)
        with torch.inference_mode(),adapter.request('drink'):
            adapter.model(input_ids=torch.tensor([[1,7,11]]),use_cache=True)
        self.assertGreater(adapter.encoding_cache_size,0)
        client.active=False
        with self.assertRaises(AimeeError):
            with adapter.request('drink'):
                self.fail('revoked session started')
        self.assertIsNone(adapter.active)

    def test_payload_larger_than_budget_is_not_retained(self):
        adapter=QwenAimeeAdapter(tiny_model(),Tokenizer(),Client(),host_memory=True,encoding_cache_bytes=1)
        self.addCleanup(adapter.close)
        with torch.inference_mode(),adapter.request('drink'):
            adapter.model(input_ids=torch.tensor([[1,7,11]]),use_cache=True)
        self.assertEqual(adapter.encoding_cache_size,0)
