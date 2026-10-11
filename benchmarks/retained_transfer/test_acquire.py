import unittest
from acquire import rule

class SchemaTests(unittest.TestCase):
    def test_rule_preserves_literal_and_order(self):
        self.assertEqual(rule('{"output_template":"pami-{verb} {noun} {adjective}"}')['output_template'],'pami-{verb} {noun} {adjective}')
    def test_rejects_unsafe_or_nonrule_payload(self):
        for raw in ['{"output_template":"{noun.x} {verb} {adjective}"}',
                    '{"output_template":"{noun} {noun} {verb}"}',
                    '{"output_template":"{noun!r} {verb} {adjective}"}',
                    '{"output_template":"{noun} {verb} {adjective}","oracle":true}',
                    '```json\n{}\n```']:
            with self.subTest(raw=raw),self.assertRaises(ValueError):rule(raw)

if __name__=='__main__':unittest.main()
