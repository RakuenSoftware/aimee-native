"""vLLM authentication must run before native body reads or source selection."""
import unittest
from vllm.entrypoints.serve.middleware.authenticate import AuthenticationMiddleware
from aimee_vllm.admission import NativeAdmission


class EnrolledAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, headers):
        owner = NativeAdmission.__new__(NativeAdmission)
        owner.poisoned = True
        owner.paused = False
        owner.config = {'selection_socket': '/unreachable'}
        owner.authentication = AuthenticationMiddleware(owner._admit, tokens=['valid-release-key'])
        events = []

        async def receive():
            raise AssertionError('unauthenticated or poisoned admission read the request body')

        async def send(event):
            events.append(event)

        await owner({'type': 'http', 'method': 'POST', 'path': '/v1/chat/completions',
                     'root_path': '', 'headers': headers}, receive, send)
        return events[0]['status']

    async def test_missing_wrong_and_wrong_scheme_credentials_fail_before_native_work(self):
        for headers in ([], [(b'authorization', b'Bearer wrong-key')],
                        [(b'authorization', b'Basic valid-release-key')]):
            self.assertEqual(await self.invoke(headers), 401)

    async def test_valid_stock_bearer_reaches_native_admission(self):
        self.assertEqual(await self.invoke([(b'authorization', b'Bearer valid-release-key')]), 503)


if __name__ == '__main__':
    unittest.main()
