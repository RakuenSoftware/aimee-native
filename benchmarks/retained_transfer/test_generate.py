import json
import string
import unittest
from generate import bundle, canonical, export
import tempfile
from pathlib import Path

class SplitTests(unittest.TestCase):
    def test_freeze_and_separation(self):
        data=bundle()
        self.assertEqual(canonical(data),canonical(bundle()))
        self.assertEqual(len(data['learner']),60)
        for learn,ev,cal in zip(data['learner'],data['evaluation'],data['calibration']):
            self.assertEqual(learn['family_id'],ev['family_id'])
            self.assertNotIn('oracle_rule',learn)
            self.assertNotIn('inputs',learn)
            for field in ('noun','verb','adjective'):
                sets=[{x['slots'][field] for x in group} for group in (learn['examples'],ev['inputs'],cal['inputs'])]
                for i in range(3):
                    for j in range(i): self.assertFalse(sets[i]&sets[j])
            template=json.loads(ev['oracle_rule'])['output_template']
            fields=[f for _,f,_,_ in string.Formatter().parse(template) if f]
            self.assertEqual(sorted(fields),['adjective','noun','verb'])
            for item in learn['examples']+ev['inputs']+cal['inputs']:
                expected=template.format(**{k:learn['lexicon'][k][v] for k,v in item['slots'].items()})
                self.assertEqual(expected,item['output'])
            self.assertEqual(len({x['input'] for x in ev['inputs']}),20)
    def test_export_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'fixture'; m=export(root)
            self.assertEqual(len(m['files']),3)
            with self.assertRaises(FileExistsError):export(root)

if __name__=='__main__':unittest.main()
