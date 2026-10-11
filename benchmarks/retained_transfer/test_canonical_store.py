import hashlib,unittest
from canonical_store import CanonicalStore

class StoreTests(unittest.TestCase):
    def candidate(self):
        text='{"output_template":"pami {noun} {verb} {adjective}"}'
        return {'family_id':'L1-F01','content':text,'content_sha256':hashlib.sha256(text.encode()).hexdigest(),'source_session':'learner-A'}
    def test_admission_preserves_exact_donor_bytes(self):
        store=CanonicalStore.__new__(CanonicalStore);candidate=self.candidate();calls=[]
        def call(route,body):
            calls.append((route,body))
            if route.endswith('/store'):return {'status':'ok','id':42}
            return {'status':'ok','memory':{'content':candidate['content']}}
        store.call=call;result=store.admit(candidate)
        self.assertEqual(result['content'],candidate['content'])
        self.assertEqual(result['canonical_record_id'],'42')
        self.assertEqual(calls[0][1]['content'],candidate['content'])
    def test_readback_mismatch_cannot_be_admitted(self):
        store=CanonicalStore.__new__(CanonicalStore)
        store.call=lambda route,body: {'status':'ok','id':42} if route.endswith('/store') else {'status':'ok','memory':{'content':'wrong'}}
        with self.assertRaises(AssertionError):store.admit(self.candidate())
    def test_changed_content_hash_refuses_before_write(self):
        store=CanonicalStore.__new__(CanonicalStore)
        store.call=lambda *args:self.fail('Write attempted despite incorrect hash')
        candidate=self.candidate();candidate['content']='modified'
        with self.assertRaises(AssertionError):store.admit(candidate)

if __name__=='__main__':unittest.main()
