import json,unittest
from datetime import datetime,timezone,timedelta
from test_local_image import LocalImageTests
from local_first import LocalFirstClient

class LocalFirstTests(LocalImageTests):
    def test_published_hit_uncovered_fallback_and_generation_withdrawal(self):
        from test_adapter import Client
        r=self.record('user','drink oolong','user')
        response={'facts':[{'id':'1','content':'drink oolong'}],'windows':[],'active_context_missing':False}
        contract={'query':'drink','limit':2,'authority':'test','grants':['user:_user'],'valid_until':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),'dependencies':[{k:r[k] for k in ['namespace','id','revision']}],'response':response}
        second=self.build('user','server',self.general,[r],generation=2,previous=self.first,read_contracts=[contract])
        self.call('publish','--view',second,'--expected',self.first)
        remote=Client([{'id':'2','content':'fresh authority result'}]);client=LocalFirstClient(self.client(),remote,'test')
        client.begin_request();self.assertEqual(client.search('drink',2),response);self.assertEqual(remote.calls,[])
        self.assertEqual(client.search('new question',2)['facts'],remote.facts);self.assertEqual(len(remote.calls),1)
        third=self.build('user','server',self.general,[],generation=3,previous=second)
        self.call('publish','--view',third,'--expected',second)
        client.begin_request();self.assertEqual(client.search('drink',2)['facts'],remote.facts)
        self.assertEqual(client.events[-1]['outcome'],'uncovered')
        with self.assertRaises(Exception):client.local._call({'op':'publish','view':second})
        self.assertEqual(json.loads((self.root/'CURRENT').read_text())['view'],third)

class AuthorizationBindingTests(unittest.TestCase):
    def test_explicit_local_denial_never_tries_remote(self):
        from aimee_client import AimeeError, AimeeRequestRejected
        for when in ('pin', 'recall'):
            with self.subTest(when=when):
                class Local:
                    authorization_id='grant'
                    def begin_request(self):
                        if when=='pin':raise AimeeRequestRejected('revoked')
                        return 'view'
                    def recall(self,*args):raise AimeeRequestRejected('revoked')
                class Remote:
                    authorization_id='grant'
                    def begin_request(self):pass
                    def search(self,*args):raise AssertionError('denial fell through to remote')
                c=LocalFirstClient(Local(),Remote(),'authority')
                if when=='pin':
                    with self.assertRaises(AimeeRequestRejected):c.begin_request()
                else:
                    c.begin_request()
                    with self.assertRaises(AimeeRequestRejected):c.search('query',2)
                self.assertFalse(c.local_ready)
                self.assertFalse(c.request_authorized)
                with self.assertRaises(AimeeError):c.search('query',2)

    def test_local_transport_failure_still_allows_authorized_remote(self):
        from aimee_client import AimeeError
        for when in ('pin', 'recall'):
            with self.subTest(when=when):
                class Local:
                    authorization_id='grant'
                    def begin_request(self):
                        if when=='pin':raise AimeeError('reader unavailable')
                        return 'view'
                    def recall(self,*args):raise AimeeError('reader unavailable')
                class Remote:
                    authorization_id='grant'
                    def begin_request(self):pass
                    def search(self,*args):return {'facts':[],'windows':[]}
                c=LocalFirstClient(Local(),Remote(),'authority')
                c.begin_request()
                self.assertEqual(c.search('query',2),{'facts':[],'windows':[]})
                self.assertTrue(c.request_authorized)

    def test_mismatched_local_binding_cannot_be_used(self):
        class Local:
            authorization_id='other-grant'
            def begin_request(self):return 'view'
            def recall(self,*args):raise AssertionError('foreign image used')
        class Remote:
            authorization_id='correct-grant'
            def begin_request(self):pass
            def search(self,*args):return {'facts':[],'windows':[]}
        c=LocalFirstClient(Local(),Remote(),'authority')
        from aimee_client import AimeeError
        with self.assertRaises(AimeeError):c.begin_request()
        with self.assertRaises(AimeeError):c.search('query',2)
        self.assertFalse(c.local_ready)

    def test_authority_revocation_cannot_fall_back_to_local(self):
        from aimee_client import AimeeError
        class Local:
            def begin_request(self):raise AssertionError('local checked after authority denial')
        class Remote:
            def begin_request(self):raise AimeeError('revoked')
        c=LocalFirstClient(Local(),Remote(),'authority')
        with self.assertRaises(AimeeError):c.begin_request()
