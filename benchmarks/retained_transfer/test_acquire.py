import json
import unittest
from acquire import checked_record, validation_outputs, revision_feedback

class TransportTests(unittest.TestCase):
    def test_retry_receives_failed_training_case_and_exact_previous_record(self):
        examples=[{'id':'train-seen','input':'seen input','slots':{'noun':'seen'},'output':'correct'}]
        feedback=revision_feedback('unchanged rule',['wrong'],examples,None)
        self.assertEqual(feedback['previous_rule'],'unchanged rule')
        self.assertEqual(feedback['training_failures'][0]['observed'],'wrong')
        self.assertEqual(feedback['training_failures'][0]['expected'],'correct')
        self.assertEqual(revision_feedback('r',['correct'],examples,None)['training_failures'],[])

    def test_written_record_is_preserved(self):
        examples=[{'id':'train-01','input':'an example input','output':'an example output'}]
        for text in ['Use verb then noun.', '```json\n{"record_schema":{"output_template":"{verb} {noun}"}}\n```']:
            self.assertEqual(checked_record(text,examples),text)
    def test_experience_is_not_a_rule(self):
        examples=[{'id':'train-01','input':'an example input','output':'an example output'}]
        for text in ['', 'train-01', 'an example output', 'x'*2001]:
            with self.assertRaises(ValueError):checked_record(text,examples)
    def test_experience_policy_is_explicit_and_does_not_rewrite_content(self):
        examples=[{'id':'train-01','input':'seen input','output':'seen output'}]
        text='Rule then noun. Worked example: seen input -> seen output'
        with self.assertRaises(ValueError):checked_record(text,examples)
        self.assertEqual(checked_record(text,examples,allow_training_examples=True),text)

    def test_validation_transport_only(self):
        outputs=['answer']*8
        for raw in [json.dumps(outputs),'```json\n'+json.dumps(outputs)+'\n```']:
            self.assertEqual(validation_outputs(raw),outputs)
        for raw in ['[]','{}',json.dumps([1]*8)]:
            with self.assertRaises(ValueError):validation_outputs(raw)

if __name__=='__main__':unittest.main()
