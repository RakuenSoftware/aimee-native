"""Rust policy + ownership bridge, no model required."""
import ctypes
import os
import unittest
from aimee_vllm.cache import DeviceCache

class Bank:
    def __init__(self, uid, size=10): self.uid=uid;self.size=size;self.loaded=False;self.loads=0
    def device_bytes(self,world): return self.size
    def reservation_bytes(self,world,rank=0): return self.size
    def activate(self,*args): self.loaded=True;self.loads+=1
    def evict(self,*args): self.loaded=False

@unittest.skipUnless(os.environ.get('AIMEE_STORE_LIBRARY'), 'set Rust store library')
class CacheTests(unittest.TestCase):
    def cache(self, budget=20):
        c=DeviceCache(ctypes.CDLL(os.environ['AIMEE_STORE_LIBRARY']),budget,'cpu',0,1)
        self.addCleanup(c.close);return c
    def test_temporary_decode_storage_counts_toward_budget(self):
        c=self.cache(budget=15);a=Bank(1,10)
        a.reservation_bytes=lambda world,rank:18
        with self.assertRaises(RuntimeError):c.ensure([a],lambda:self.fail('unexpected eviction'))
        self.assertFalse(a.loaded)
    def test_eviction_clears_pointer_owners_before_bank_release_and_reload(self):
        c=self.cache();a,b,d=Bank(1),Bank(2),Bank(3);events=[]
        c.ensure([a,b],lambda:None)
        c.ensure([b,d],lambda:events.append((a.loaded,b.loaded)))
        self.assertEqual(events,[(True,True)]);self.assertFalse(a.loaded);self.assertTrue(b.loaded)
        c.ensure([a,d],lambda:None)
        self.assertEqual(a.loads,2);self.assertEqual(c.stats['resident_bytes'],20)
    def test_pinned_overflow_never_evicts_active_banks(self):
        c=self.cache();a,b,d=Bank(1),Bank(2),Bank(3)
        c.ensure([a,b],lambda:None)
        with self.assertRaises(RuntimeError):c.ensure([a,b,d],lambda:self.fail('evicted active banks'))
        self.assertTrue(a.loaded and b.loaded);self.assertFalse(d.loaded)
        c.ensure([a,b],lambda:None);self.assertEqual(a.loads,1)
    def test_upload_failure_poisoned_instead_of_reusing_partial_plan(self):
        c=self.cache();a=Bank(1)
        def fail(*args):raise RuntimeError('synthetic allocation failure')
        a.activate=fail
        with self.assertRaises(RuntimeError):c.ensure([a],lambda:None)
        self.assertTrue(c.poisoned)
        with self.assertRaises(RuntimeError):c.ensure([],lambda:None)
