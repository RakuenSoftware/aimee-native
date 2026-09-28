import json
import tempfile
import unittest
from pathlib import Path
from swe_gpu_handoff import inspect


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ids = ['task-' + str(i) for i in range(31)] + ['psf__requests-2193']
        (self.root / 'tasks.json').write_text(json.dumps([{'instance_id': i} for i in self.ids]))
        for iid in self.ids:
            for arm in ('source-control', 'source-learn-1'):
                p = self.root / 'results' / arm / iid / 'result.json'
                p.parent.mkdir(parents=True)
                p.write_text(json.dumps(dict(instance_id=iid, arm=arm, resolved=False)))
        self.final = self.root / 'results/source-learn-1/psf__requests-2193'

    def submitted(self):
        (self.final / 'result.json').unlink()
        (self.final / 'trajectory.json').write_text(json.dumps({
            'info': {'exit_status': 'Submitted'},
            'messages': [{'role': 'exit', 'extra': {'exit_status': 'Submitted'}}]}))

    def test_all_grades_complete(self):
        self.assertEqual(inspect(self.root), dict(gpu_ready=True, grades_complete=True, pending=[]))

    def test_final_cpu_grade_can_overlap_certification(self):
        self.submitted()
        d = inspect(self.root)
        self.assertTrue(d['gpu_ready'])
        self.assertFalse(d['grades_complete'])

    def test_other_pending_attempt_prevents_handoff(self):
        self.submitted()
        (self.root / 'results/source-learn-1/task-0/result.json').unlink()
        self.assertFalse(inspect(self.root)['gpu_ready'])

    def test_active_final_generation_prevents_handoff(self):
        self.submitted()
        (self.final / 'trajectory.json').write_text(json.dumps({'messages': [{'role': 'assistant'}]}))
        self.assertFalse(inspect(self.root)['gpu_ready'])

    def test_infrastructure_failure_is_not_completion(self):
        p = self.final / 'result.json'
        d = json.loads(p.read_text());d['resolved'] = None;p.write_text(json.dumps(d))
        with self.assertRaises(ValueError):inspect(self.root)

    def test_mismatched_identity_is_rejected(self):
        p = self.final / 'result.json'
        d = json.loads(p.read_text());d['arm'] = 'source-control';p.write_text(json.dumps(d))
        with self.assertRaises(ValueError):inspect(self.root)
