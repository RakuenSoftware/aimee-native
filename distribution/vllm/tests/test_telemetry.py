import unittest
from aimee_vllm.telemetry import Stages

class TelemetryTests(unittest.TestCase):
    def test_disabled_is_empty_and_preserves_exception(self):
        s=Stages()
        with self.assertRaisesRegex(ValueError,'original'):
            with s.measure('selection_rpc'):raise ValueError('original')
        self.assertEqual(s.snapshot()['stages'],{})
    def test_failures_are_separate_and_snapshots_do_not_alias(self):
        s=Stages(True)
        with s.measure('selection_rpc'):pass
        with self.assertRaises(KeyboardInterrupt):
            with s.measure('selection_rpc'):raise KeyboardInterrupt()
        snap=s.snapshot();snap['stages']['selection_rpc_success']['count']=100
        self.assertEqual(s.snapshot()['stages']['selection_rpc_success']['count'],1)
        self.assertEqual(s.snapshot()['stages']['selection_rpc_failed']['count'],1)
        self.assertGreaterEqual(s.snapshot()['stages']['selection_rpc_failed']['total_ns'],0)
    def test_configuration_is_not_truthiness(self):
        for value in ('false',1,None):
            with self.assertRaises(ValueError):Stages(value)

import ctypes
import os
from aimee_vllm.cache import DeviceCache

@unittest.skipUnless(os.environ.get('AIMEE_STORE_LIBRARY'),'set current Rust policy library')
class CacheTelemetryTests(unittest.TestCase):
    def test_activation_and_failed_plan_have_separate_bounded_counters(self):
        from test_cache import Bank
        cache=DeviceCache(ctypes.CDLL(os.environ['AIMEE_STORE_LIBRARY']),10,'cpu',0,1,telemetry=True)
        self.addCleanup(cache.close)
        bank=Bank(1)
        cache.ensure([bank],lambda:None)
        cache.ensure([bank],lambda:None)
        with self.assertRaises(RuntimeError):cache.ensure([bank,Bank(2)],lambda:None)
        rows=cache.stages.snapshot()['stages']
        self.assertEqual(rows['activation_and_cache_success']['count'],2)
        self.assertEqual(rows['activation_and_cache_failed']['count'],1)
        self.assertEqual(rows['bank_activation_success']['count'],1)
        self.assertEqual(bank.loads,1)
    def test_failed_upload_remains_poisoned_with_telemetry_enabled(self):
        from test_cache import Bank
        cache=DeviceCache(ctypes.CDLL(os.environ['AIMEE_STORE_LIBRARY']),10,'cpu',0,1,telemetry=True)
        self.addCleanup(cache.close)
        bank=Bank(1)
        def fail(*args,**kwargs):raise RuntimeError('allocation failed')
        bank.activate=fail
        with self.assertRaises(RuntimeError):cache.ensure([bank],lambda:None)
        self.assertTrue(cache.poisoned)
        self.assertEqual(cache.stages.snapshot()['stages']['bank_activation_failed']['count'],1)
