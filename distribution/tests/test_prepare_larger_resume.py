"""Protect archived outcomes while supplementing an ungraded infrastructure case."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from prepare_larger_resume import prepare


class Resume(unittest.TestCase):
    def test_original_is_immutable_and_patch_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); old = root/'original'; old.mkdir(); grade = root/'grade'; grade.mkdir()
            (old/'status.json').write_text('{"status":"failed"}')
            for name in ['manifest.json','frozen-inputs.json','run.py','larger_regression.py']:
                (old/name).write_text('fixture')
            relative = Path('results/text/task/result.json'); p=old/relative; p.parent.mkdir(parents=True)
            raw=json.dumps({'resolved':None,'grade_status':'infrastructure_error','model_patch':'unchanged patch','grade_timeout_seconds':300}).encode()
            p.write_bytes(raw)
            passed=old/'results/control/other/result.json';passed.parent.mkdir(parents=True);passed.write_text('{"resolved":true}')
            record={'status':'graded','resolved':False,'agent_rerun':False,'arm':'text','instance_id':'task',
                    'original_result_sha256':hashlib.sha256(raw).hexdigest(),'patch_sha256':'0'*64,'timeout':3600}
            (grade/'status.json').write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,'patch changed'):prepare(old,root/'bad',grade)
            self.assertFalse((root/'bad').exists())
            record['patch_sha256']=hashlib.sha256(b'unchanged patch').hexdigest()
            (grade/'status.json').write_text(json.dumps(record));prepare(old,root/'resumed',grade)
            self.assertEqual(p.read_bytes(),raw)
            self.assertEqual((root/'resumed'/relative.parent/'result.original.json').read_bytes(),raw)
            self.assertEqual((root/'resumed/results/control/other/result.json').read_bytes(),passed.read_bytes())
            self.assertIs(json.loads((root/'resumed'/relative).read_text())['resolved'],False)
            with self.assertRaises(FileExistsError):prepare(old,root/'resumed',grade)


if __name__ == '__main__':
    unittest.main()
