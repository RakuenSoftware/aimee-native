import audit
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from audit import distribution, summarize


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.condition = dict(model="frozen-model-r1", selector="attention-spans",
                              schedule="decode", archive_records=1000, context_tokens=64,
                              position_budget=128, cache_state="warm", encoding_granularity="record")
        self.trace = {"elapsed_ms": 12, "native_reads": 3, "memory_encoding_passes": 1,
                      "native_bank_application_cpu_ns": 1000,
                      "recall_events": [
                          {"source_selection_ns": 2000000, "encoding_elapsed_ms": 4,
                           "memory_encoding_tokens": 32, "status": "bank_updated"},
                          {"source_selection_ns": 1000000, "encoding_elapsed_ms": 0,
                           "status": "bank_unchanged"}]}

    def write(self, traces, entries=None):
        samples = []
        for i, trace in enumerate(traces):
            name = f"trace-{i}.json"
            (self.root / name).write_text(json.dumps(trace))
            samples.append(dict(task_id=f"task-{i}", trace=name, condition=self.condition,
                                correct=True, selection_correct=True))
        if entries:
            for i, patch in enumerate(entries):
                samples[i].update(patch)
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps(dict(schema="native-addressing-v1", samples=samples)))
        return manifest

    def test_complete_cost_units_hashes_and_no_content_export(self):
        self.trace["answer"] = "private answer"
        report = summarize(self.write([self.trace]))
        group = report["groups"][0]
        self.assertEqual(group["timings_ms"]["selection_ms"]["success"]["median"], 3)
        self.assertEqual(group["timings_ms"]["encoding_cache_ms"]["success"]["median"], 4)
        self.assertEqual(group["timings_ms"]["bank_application_cpu_ms"]["success"]["median"], .001)
        self.assertEqual(group["recall_statuses"]["bank_unchanged"], 1)
        self.assertEqual(report["samples"][0]["trace_sha256"],
                         hashlib.sha256((self.root / "trace-0.json").read_bytes()).hexdigest())
        self.assertNotIn("private answer", json.dumps(report))

    def test_partial_cost_is_not_reported_as_complete(self):
        del self.trace["recall_events"][1]["encoding_elapsed_ms"]
        report = summarize(self.write([self.trace]))
        group = report["groups"][0]
        self.assertEqual(group["timings_ms"]["encoding_cache_ms"]["success"]["n"], 0)
        self.assertEqual(group["event_timing_coverage"]["encoding_cache_ms"],
                         {"observed_events": 1, "events": 2})

    def test_missing_events_and_missing_gpu_time_are_unknown(self):
        for events in (None, []):
            self.trace["recall_events"] = events
            report = summarize(self.write([self.trace]))
            group = report["groups"][0]
            self.assertEqual(group["timings_ms"]["selection_ms"]["success"]["n"], 0)
            self.assertIsNone(group["timings_ms"]["attention_gpu_ms"]["success"]["median"])

    def test_failed_requests_do_not_contaminate_success_latency(self):
        bad = {"status": "failed", "elapsed_ms": 1000, "recall_events": []}
        report = summarize(self.write([self.trace, bad], [{}, {"correct": False}]))
        group = report["groups"][0]
        self.assertEqual(group["failed"], 1)
        self.assertEqual(group["elapsed_ms"]["success"]["median"], 12)
        self.assertEqual(group["elapsed_ms"]["failed"]["median"], 1000)
        self.assertEqual(group["outcomes"]["runtime_failure"], 1)

    def test_conditions_and_repeat_counts_remain_separate(self):
        other = dict(self.condition, archive_records=100000)
        report = summarize(self.write([self.trace] * 3, [
            {"task_id": "same", "replicate": 0},
            {"task_id": "same", "replicate": 1}, {"condition": other}]))
        self.assertEqual(len(report["groups"]), 2)
        group = next(g for g in report["groups"] if g["requests"] == 2)
        self.assertEqual(group["distinct_tasks"], 1)

    def test_selection_and_consumption_failures_are_distinct(self):
        report = summarize(self.write([self.trace] * 3, [
            {"correct": False, "selection_correct": False},
            {"correct": False, "selection_correct": True},
            {"correct": False, "selection_correct": None}]))
        self.assertEqual(report["groups"][0]["outcomes"], {
            "selection_failure": 1, "consumption_or_execution_failure": 1,
            "unattributed_or_unscored": 1})

    def test_observed_position_violation_is_reported(self):
        self.trace["recall_events"][0]["memory_encoding_tokens"] = 129
        group = summarize(self.write([self.trace]))["groups"][0]
        self.assertEqual(group["observed_position_budget_violations"], 1)

    def test_negative_boolean_and_nonfinite_measurements_fail(self):
        for value in (-1, True, float("nan"), float("inf")):
            with self.subTest(value=value):
                trace = dict(self.trace, elapsed_ms=value)
                with self.assertRaises(ValueError):
                    summarize(self.write([trace]))

    def test_duplicate_task_and_duplicate_json_keys_fail(self):
        manifest = self.write([self.trace] * 2, [{}, {"task_id": "task-0"}])
        with self.assertRaisesRegex(ValueError, "duplicate condition"):
            summarize(manifest)
        (self.root / "trace-0.json").write_text('{"elapsed_ms":1,"elapsed_ms":2}')
        manifest = self.root / "manifest.json"
        raw = json.loads(manifest.read_text())
        raw["samples"] = raw["samples"][:1]
        manifest.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            summarize(manifest)

    def test_missing_conditions_invalid_counts_and_false_success_fail(self):
        condition = dict(self.condition)
        del condition["schedule"]
        with self.assertRaises(ValueError):
            summarize(self.write([self.trace], [{"condition": condition}]))
        with self.assertRaises(ValueError):
            summarize(self.write([dict(self.trace, native_reads=1.5)]))
        with self.assertRaises(ValueError):
            summarize(self.write([dict(self.trace, status="failed")]))

    def test_cli_refuses_existing_output_and_writes_private_report(self):
        manifest = self.write([self.trace])
        output = self.root / "report.json"
        cmd = [sys.executable, str(Path(__file__).with_name("audit.py")),
               str(manifest), "--output", str(output)]
        result = subprocess.run(cmd, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        before = output.read_bytes()
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        result = subprocess.run(cmd, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(output.read_bytes(), before)

    def test_nearest_rank_tail_and_empty_distribution(self):
        self.assertEqual(distribution([1, 2, 3, 4, 5])["p95"], 5)
        self.assertEqual(distribution([])["n"], 0)
        self.assertIsNone(distribution([])["median"])

    def metrics(self):
        return dict(schema="native-memory-metrics-v1", addressing_attempts=2,
                    addressing_failures=0, active_positions=16, peak_active_positions=64,
                    active_records=1, peak_active_records=3, active_encoded_bytes=512,
                    peak_active_encoded_bytes=2048,
                    encoded_bytes_scope="logical-kv-across-native-layers",
                    addressing_timing="wall-including-bank-preparation-and-host-readback")

    def test_runtime_peaks_cover_shrink_and_failed_cleanup(self):
        metrics = self.metrics()
        trace = dict(self.trace, status="failed", native_memory_metrics=metrics,
                     native_addressing_ns=2000000)
        # Cleanup has removed current banks, but lifetime peaks must survive.
        for field in ("active_positions", "active_records", "active_encoded_bytes"):
            metrics[field] = 0
        report = summarize(self.write([trace], [{"correct": False}]))
        group = report["groups"][0]
        self.assertEqual(group["observed_peak_positions"]["median"], 64)
        self.assertEqual(group["native_metrics"]["peak_active_encoded_bytes"]["median"], 2048)
        self.assertEqual(group["timings_ms"]["addressing_ms"]["failed"]["median"], 2)
        self.assertEqual(group["native_metrics_coverage"], 1)
        self.assertEqual(group["position_coverage"], {"post-recall-working-sets": 1})

    def test_runtime_metrics_reject_inconsistent_or_unknown_scopes(self):
        for patch in ({"active_positions": 65}, {"addressing_failures": 3},
                      {"peak_active_records": True}, {"encoded_bytes_scope": "gpu-rss"},
                      {"addressing_timing": "gpu-kernel-only"}, {"schema": "future"}):
            with self.subTest(patch=patch):
                metrics = dict(self.metrics(), **patch)
                with self.assertRaises(ValueError):
                    summarize(self.write([dict(self.trace, native_memory_metrics=metrics)]))

    def test_explicit_nonencoding_paths_complete_timing_coverage(self):
        trace = dict(self.trace, recall_events=[
            dict(status="empty", source_selection_ns=1000, encoding_elapsed_ms=0,
                 encoding_outcome="not_started", recall_elapsed_ns=2000),
            dict(status="bank_unchanged", source_selection_ns=2000, encoding_elapsed_ms=.001,
                 encoding_outcome="unchanged", recall_elapsed_ns=4000)])
        group = summarize(self.write([trace]))["groups"][0]
        self.assertAlmostEqual(group["timings_ms"]["recall_ms"]["success"]["median"], .006)
        self.assertEqual(group["timings_ms"]["encoding_cache_ms"]["success"]["n"], 1)


    def test_schedule_coverage_budget_and_skips_are_validated(self):
        self.trace["native_memory_metrics"] = {
            "schema":"native-memory-metrics-v1","addressing_attempts":2,"addressing_failures":0,
            "active_positions":0,"peak_active_positions":0,"active_records":0,"peak_active_records":0,
            "active_encoded_bytes":0,"peak_active_encoded_bytes":0,
            "encoded_bytes_scope":"logical-kv-across-native-layers",
            "addressing_timing":"wall-including-bank-preparation-and-host-readback",
            "source_reads":3,"scheduled_skips":4,"exhausted_steps":2,
            "schedule":{"mode":"bounded-refresh","interval_steps":4,"max_source_reads":3}}
        report=summarize(self.write([self.trace]))
        self.assertEqual(report["groups"][0]["native_metrics"]["source_reads"]["median"],3)
        for patch in ({"source_reads":4},{"exhausted_steps":5},{"scheduled_skips":False}):
            with self.subTest(patch=patch):
                bad=dict(self.trace,native_memory_metrics=dict(self.trace["native_memory_metrics"],**patch))
                with self.assertRaises(ValueError):summarize(self.write([bad]))

class HybridMetricTests(unittest.TestCase):
    def metrics(self):
        return dict(schema="native-memory-metrics-v1", addressing_attempts=0, addressing_failures=0,
                    active_positions=0, peak_active_positions=0, active_records=0, peak_active_records=0,
                    active_encoded_bytes=0, peak_active_encoded_bytes=0,
                    encoded_bytes_scope="logical-kv-across-native-layers",
                    addressing_timing="wall-including-bank-preparation-and-host-readback")
    def test_absent_hybrid_state_is_unknown_not_zero(self):
        result=audit.native_metrics({"native_memory_metrics":self.metrics()})
        self.assertIsNone(result["peak_active_recurrent_bytes"])
    def test_complete_hybrid_metrics_and_invalid_partial_extent(self):
        m=self.metrics();m.update(active_recurrent_bytes=16,peak_active_recurrent_bytes=32,native_replays=1,replay_wall_ns=20)
        self.assertEqual(audit.native_metrics({"native_memory_metrics":m})["peak_active_recurrent_bytes"],32)
        for changes in ({"active_recurrent_bytes":33},{"native_replays":True},{"replay_wall_ns":None}):
            with self.assertRaises(ValueError):audit.native_metrics({"native_memory_metrics":{**m,**changes}})

if __name__ == "__main__":
    unittest.main()
