import unittest
from types import SimpleNamespace
from prefix_receiver import cache_tensors
class CacheInspectionTests(unittest.TestCase):
    def test_all_hybrid_states_are_inspected(self):
        kv,conv,recurrent=object(),object(),object()
        cache=SimpleNamespace(layers=[SimpleNamespace(keys=kv,values=None),
            SimpleNamespace(conv_states={0:conv,1:None},recurrent_states={0:recurrent})])
        self.assertEqual(list(cache_tensors(cache)),[('0.keys',kv),('1.conv_states.0',conv),('1.recurrent_states.0',recurrent)])
    def test_populated_additional_states_cannot_be_ignored(self):
        a,b=object(),object()
        cache=SimpleNamespace(layers=[SimpleNamespace(recurrent_states={1:b,0:a})])
        self.assertEqual(list(cache_tensors(cache)),[('0.recurrent_states.0',a),('0.recurrent_states.1',b)])
if __name__=='__main__':unittest.main()
