"""The replay guard must accept CPU-only grading but reject active inference."""
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

REPO = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('replay_guard', REPO/'benchmarks/swe_learning/replay_repetition.py')
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class ReplayHandoff(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        for name, status in [('source-learning-20260927', 'complete'), ('broader-source-learning-20260928', 'running')]:
            p = self.root/name
            p.mkdir()
            (p/'status.json').write_text(json.dumps({'status': status}))

    def test_pending_final_cpu_grade_allows_replay(self):
        report = {'gpu_ready': True, 'grades_complete': False, 'pending': [['psf__requests-2193', 'source-learn-1']]}
        with patch.object(replay.subprocess, 'check_output', return_value=json.dumps(report)):
            self.assertEqual(replay.require_inference_complete(self.root), report)

    def test_active_inference_rejects_replay(self):
        with patch.object(replay.subprocess, 'check_output', return_value='{"gpu_ready":false}'):
            with self.assertRaises(RuntimeError):replay.require_inference_complete(self.root)

    def test_failed_study_rejects_before_publication(self):
        (self.root/'broader-source-learning-20260928/status.json').write_text('{"status":"failed"}')
        with patch.object(replay.subprocess, 'check_output') as call:
            with self.assertRaises(RuntimeError):replay.require_inference_complete(self.root)
            call.assert_not_called()

    def test_primary_still_running_rejects_replay(self):
        (self.root/'source-learning-20260927/status.json').write_text('{"status":"running"}')
        with patch.object(replay.subprocess, 'check_output') as call:
            with self.assertRaises(RuntimeError):replay.require_inference_complete(self.root)
            call.assert_not_called()
