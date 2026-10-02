import copy
import unittest
from coverage import validate_records, validate_encoding

class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.refs=[dict(namespace='test',id=str(i),revision='1') for i in range(64)]
        self.facts=[dict(id='test:'+r['id'],memory_ref=r,content='Fact '+r['id']) for r in self.refs]
        self.ids=[f['id'] for f in self.facts]
        self.tokens=list(range(320))
        self.state=dict(recall_events=[dict(status='bank_updated',bank_memory_ids=self.ids)],memory_token_ids=self.tokens,memory_encoding_tokens=len(self.tokens))
    def test_complete_set(self):
        self.assertEqual(validate_records(self.facts,self.refs),self.ids)
        validate_encoding(self.state,self.ids,self.tokens)
    def test_single_record_response_rejected(self):
        with self.assertRaises(ValueError):validate_records(self.facts[:1],self.refs)
    def test_limit_four_response_rejected(self):
        with self.assertRaises(ValueError):validate_records(self.facts[:4],self.refs)
    def test_wrong_revision_rejected(self):
        facts=copy.deepcopy(self.facts);facts[-1]['memory_ref']['revision']='old'
        with self.assertRaises(ValueError):validate_records(facts,self.refs)
    def test_one_record_encoded_rejected(self):
        state=copy.deepcopy(self.state);state['recall_events'][0]['bank_memory_ids']=self.ids[:1]
        with self.assertRaises(ValueError):validate_encoding(state,self.ids,self.tokens)
    def test_truncated_encoder_input_rejected(self):
        state=copy.deepcopy(self.state);state['memory_token_ids']=self.tokens[:5]
        with self.assertRaises(ValueError):validate_encoding(state,self.ids,self.tokens)
    def test_reordered_bank_rejected(self):
        state=copy.deepcopy(self.state);state['recall_events'][0]['bank_memory_ids']=list(reversed(self.ids))
        with self.assertRaises(ValueError):validate_encoding(state,self.ids,self.tokens)

if __name__=='__main__':unittest.main()
