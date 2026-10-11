import unittest
from receiver_plan import messages,record_for,shuffled_records,common_prefix
class PlanTests(unittest.TestCase):
    def test_same_written_record_text_and_native(self):
        f={'family_id':'F','language':'L','lexicon':{'noun':{'cat':'pami'}}}
        item={'input':'cat','slots':{'noun':'cat'}};r={'content':'```json\n{"nested":"raw rule"}\n```'}
        self.assertEqual(messages(f,item,'Native',r,{}),messages(f,item,'Text',r,{}))
    def test_shuffle_is_occupied_distinct_and_language_local(self):
        records=[{'family_id':str(i),'language':'L'} for i in range(3)]+[{'family_id':'solo','language':'other'}]
        shuffled=shuffled_records(records)
        self.assertEqual(set(shuffled),{'0','1','2'})
        self.assertEqual({r['family_id'] for r in shuffled.values()},{'0','1','2'})
        self.assertTrue(all(k!=r['family_id'] for k,r in shuffled.items()))
    def test_missing_record_is_not_oracle_fallback(self):
        self.assertIsNone(record_for('Native',{'family_id':'missing'},{},{},{}))
    def test_prefix_reconstructs_every_full_request(self):
        full=[[1,2,3,4],[1,2,5,6]];prefix=common_prefix(full)
        self.assertEqual(prefix,[1,2])
        for ids in full:self.assertEqual(prefix+ids[len(prefix):],ids)
if __name__=='__main__':unittest.main()
