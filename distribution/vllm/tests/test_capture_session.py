"""Preparation can follow completed live requests but cannot share a forward."""
from types import SimpleNamespace
import unittest
from aimee_vllm.capture_session import CaptureSession


class CaptureOwnershipTests(unittest.TestCase):
    def session(self):
        session = CaptureSession()
        session.request = None
        session.tokens = [7, 11]
        return session

    def scheduled(self, **values):
        defaults = dict(num_scheduled_tokens={}, scheduled_new_reqs=[], finished_req_ids=[])
        defaults.update(values)
        return SimpleNamespace(**defaults)

    def test_old_request_cleanup_before_exclusive_capture(self):
        session = self.session()
        session.begin(self.scheduled(finished_req_ids=['previous-live-request']))
        request = SimpleNamespace(req_id='capture', prompt_token_ids=[7, 11])
        session.begin(self.scheduled(num_scheduled_tokens={'capture':2}, scheduled_new_reqs=[request],
                                     finished_req_ids=['another-completed-request']))
        self.assertEqual(session.request, 'capture')

    def test_foreign_live_tokens_and_finished_capture_are_rejected(self):
        for scheduled, finished in [({'capture':2, 'foreign':1}, []), ({'capture':2}, ['capture'])]:
            session = self.session()
            session.request = 'capture'
            with self.assertRaisesRegex(RuntimeError, 'uninterrupted prefill'):
                session.begin(self.scheduled(num_scheduled_tokens=scheduled, finished_req_ids=finished))


if __name__ == '__main__':
    unittest.main()
