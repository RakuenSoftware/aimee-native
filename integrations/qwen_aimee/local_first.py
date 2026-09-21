"""Read-only local reuse of Aimee-published decisions, with real Aimee fallback.

No learning, response publication, or mutation API. Uncovered requests do not
use lexical guesses. The authority controls exact-request grants and expiry.
"""
from aimee_client import AimeeError, AimeeRequestRejected


class LocalFirstClient:
    def __init__(self, local, authority, authority_id):
        self.local, self.authority, self.authority_id = local, authority, authority_id
        self.events = []
        self.local_ready = False
        self.authorization_id = None
        self.request_authorized = False

    def begin_request(self):
        self.request_authorized = False
        self.local_ready = False
        self.events = []
        if hasattr(self.authority, 'begin_request'):
            self.authority.begin_request()
        self.authorization_id = getattr(self.authority, 'authorization_id', None)
        try:
            view = self.local.begin_request()
        except AimeeRequestRejected:
            # An explicit denial is authoritative for this request, even if
            # the remote guard has not yet observed the permission change.
            raise
        except AimeeError:
            self.local_ready = False
            self.request_authorized = True  # The configured authority remains usable.
            return None
        local_binding = getattr(self.local, 'authorization_id', None)
        if self.authorization_id is not None and local_binding != self.authorization_id:
            self.local_ready = False
            raise AimeeError('local and remote authorization differ')
        self.local_ready = True
        self.request_authorized = True
        return view

    def search(self, query, limit):
        if not self.request_authorized:
            raise AimeeError('memory request has no valid authorization binding')
        outcome = 'local_unavailable'
        if self.local_ready:
            try:
                result = self.local.recall(query, limit, self.authority_id)
                outcome = result['outcome']
                if outcome == 'hit':
                    self.events.append({'query': query, 'outcome': outcome, 'remote': False, 'view': result['view']})
                    return result['response']
            except AimeeRequestRejected:
                self.local_ready = False
                self.request_authorized = False
                raise
            except AimeeError:
                self.local_ready = False
        self.events.append({'query': query, 'outcome': outcome, 'remote': True})
        try:
            return self.authority.search(query, limit)
        except AimeeRequestRejected:
            # A later local hit must not revive a request denied by Aimee.
            self.local_ready = False
            self.request_authorized = False
            raise

    def close(self):
        self.local.close()
        self.authority.close()
