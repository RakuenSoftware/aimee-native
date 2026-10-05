"""Audit native-memory traces without launching models or rewriting evidence."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import statistics


CONDITION_FIELDS = {
    "model", "selector", "schedule", "archive_records", "context_tokens",
    "position_budget", "cache_state", "encoding_granularity",
}
STAGES = {
    "selection_ms": ("source_selection_ns", 1e-6),
    "encoding_cache_ms": ("encoding_elapsed_ms", 1),
    "recall_ms": ("recall_elapsed_ns", 1e-6),
}
REQUEST_STAGES = {
    "native_ready_ms": ("native_ready_ns", 1e-6),
    "bank_application_cpu_ms": ("native_bank_application_cpu_ns", 1e-6),
    "addressing_ms": ("native_addressing_ns", 1e-6),
    "activation_ms": ("native_activation_ns", 1e-6),
    "attention_gpu_ms": ("native_attention_gpu_ns", 1e-6),
}


def number(value, name):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return value


def integer(value, name):
    number(value, name)
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value


def distribution(values):
    values = sorted(values)
    if not values:
        return {"n": 0, "median": None, "p95": None, "maximum": None}
    return {"n": len(values), "median": statistics.median(values),
            "p95": values[math.ceil(.95 * len(values)) - 1], "maximum": values[-1]}


def optional_number(obj, key, scale=1):
    value = obj.get(key)
    return None if value is None else number(value, key) * scale


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def read_json(path):
    raw = path.read_bytes()
    return json.loads(raw, object_pairs_hook=unique_object), hashlib.sha256(raw).hexdigest()


def native_metrics(trace):
    metrics = trace.get("native_memory_metrics")
    if metrics is None:
        return None
    if not isinstance(metrics, dict) or metrics.get("schema") != "native-memory-metrics-v1":
        raise ValueError("unsupported native memory metrics schema")
    fields = ("addressing_attempts", "addressing_failures", "active_positions",
              "peak_active_positions", "active_records", "peak_active_records",
              "active_encoded_bytes", "peak_active_encoded_bytes")
    result = {key: integer(metrics.get(key), key) for key in fields}
    for current, peak in (("active_positions", "peak_active_positions"),
                          ("active_records", "peak_active_records"),
                          ("active_encoded_bytes", "peak_active_encoded_bytes")):
        if result[current] > result[peak]:
            raise ValueError(f"{current} exceeds its observed peak")
    if result["addressing_failures"] > result["addressing_attempts"]:
        raise ValueError("addressing failures exceed attempts")
    if metrics.get("encoded_bytes_scope") != "logical-kv-across-native-layers":
        raise ValueError("unknown encoded bytes scope")
    if metrics.get("addressing_timing") != "wall-including-bank-preparation-and-host-readback":
        raise ValueError("unknown addressing timing scope")
    hybrid = ("active_recurrent_bytes", "peak_active_recurrent_bytes", "native_replays", "replay_wall_ns")
    if any(key in metrics for key in hybrid):
        result.update({key: integer(metrics.get(key), key) for key in hybrid})
        if result["active_recurrent_bytes"] > result["peak_active_recurrent_bytes"]:
            raise ValueError("recurrent bytes exceed observed peak")
    else:
        result.update({key: None for key in hybrid})
    scheduling = ("source_reads", "scheduled_skips", "exhausted_steps")
    if any(key in metrics for key in scheduling) or "schedule" in metrics:
        for key in scheduling:
            result[key] = integer(metrics.get(key), key)
        policy = metrics.get("schedule")
        if not isinstance(policy, dict) or set(policy) != {"mode", "interval_steps", "max_source_reads"}:
            raise ValueError("complete schedule policy required")
        if policy["mode"] not in ("every-step", "preload-only", "bounded-refresh"):
            raise ValueError("unknown schedule mode")
        if integer(policy["interval_steps"], "interval_steps") < 1:
            raise ValueError("positive refresh interval required")
        limit = policy["max_source_reads"]
        if limit is not None:
            if integer(limit, "max_source_reads") < 1 or result["source_reads"] > limit:
                raise ValueError("source reads exceed schedule budget")
        if policy["mode"] == "bounded-refresh" and limit is None:
            raise ValueError("bounded refresh requires read budget")
        if result["exhausted_steps"] > result["scheduled_skips"]:
            raise ValueError("exhausted steps exceed skipped steps")
        result["schedule"] = policy
    else:
        result.update({key: None for key in scheduling})
        result["schedule"] = None
    return result


def load_samples(manifest_path):
    manifest, digest = read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("schema") != "native-addressing-v1":
        raise ValueError("expected native-addressing-v1 manifest")
    if not isinstance(manifest.get("samples"), list) or not manifest["samples"]:
        raise ValueError("manifest needs nonempty samples")
    samples, seen = [], set()
    for entry in manifest["samples"]:
        if not isinstance(entry, dict):
            raise ValueError("sample must be an object")
        condition = entry.get("condition")
        if not isinstance(condition, dict) or set(condition) != CONDITION_FIELDS:
            raise ValueError("condition must specify exactly the documented dimensions")
        for key in CONDITION_FIELDS:
            value = condition[key]
            if key in {"archive_records", "context_tokens", "position_budget"}:
                integer(value, key)
            elif not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} must be a nonempty string")
        task = entry.get("task_id")
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task_id must be a nonempty string")
        replicate = integer(entry.get("replicate", 0), "replicate")
        identity = (json.dumps(condition, sort_keys=True), task, replicate)
        if identity in seen:
            raise ValueError("duplicate condition/task/replicate")
        seen.add(identity)
        for key in ("correct", "selection_correct"):
            if entry.get(key) is not None and type(entry[key]) is not bool:
                raise ValueError(f"{key} must be a boolean or null")
        if not isinstance(entry.get("trace"), str) or not entry["trace"]:
            raise ValueError("trace must be a path")
        path = manifest_path.parent / entry["trace"]
        trace, trace_digest = read_json(path)
        if not isinstance(trace, dict):
            raise ValueError("trace must be an object")
        if trace.get("status") not in (None, "success", "failed"):
            raise ValueError("unsupported trace status")
        failed = trace.get("status") == "failed"
        if failed and entry.get("correct") is True:
            raise ValueError("failed trace cannot be scored correct")
        elapsed = optional_number(trace, "elapsed_ms")
        events = trace.get("recall_events")
        if events is not None and (not isinstance(events, list) or
                                   any(not isinstance(e, dict) for e in events)):
            raise ValueError("recall_events must be an array of objects or null")
        timings = {}
        coverage = {}
        for stage, (key, scale) in STAGES.items():
            values = [optional_number(e, key, scale) for e in events or []]
            present = [v for v in values if v is not None]
            # A partial sum is not a complete request cost. Absent events are unknown.
            timings[stage] = sum(present) if values and len(present) == len(values) else None
            coverage[stage] = {"observed_events": len(present), "events": len(values)}
        for stage, (key, scale) in REQUEST_STAGES.items():
            timings[stage] = optional_number(trace, key, scale)
        counts = {key: None if trace.get(key) is None else integer(trace[key], key)
                  for key in ("native_reads", "memory_encoding_passes")}
        positions = [integer(e["memory_encoding_tokens"], "memory_encoding_tokens")
                     for e in events or [] if e.get("memory_encoding_tokens") is not None]
        metrics = native_metrics(trace)
        if any(not isinstance(e.get("status", "unlabelled"), str) for e in events or []):
            raise ValueError("event status must be a string")
        status_counts = Counter(e.get("status", "unlabelled") for e in events or [])
        samples.append({"condition": condition, "task_id": task, "replicate": replicate,
                        "trace_sha256": trace_digest, "failed": failed,
                        "correct": entry.get("correct"),
                        "selection_correct": entry.get("selection_correct"),
                        "elapsed_ms": elapsed, "timings": timings,
                        "event_timing_coverage": coverage, "counts": counts,
                        "recall_events": None if events is None else len(events),
                        "recall_statuses": dict(status_counts),
                        "native_memory_metrics": metrics,
                        "position_coverage": "post-recall-working-sets" if metrics else "encoding-events-only",
                        "observed_peak_positions": metrics["peak_active_positions"] if metrics else
                        (max(positions) if positions else None)})
    return digest, samples


def outcome(sample):
    if sample["failed"]:
        return "runtime_failure"
    if sample["selection_correct"] is False:
        return "selection_failure"
    if sample["correct"] is False and sample["selection_correct"] is True:
        return "consumption_or_execution_failure"
    if sample["correct"] is True:
        return "correct"
    return "unattributed_or_unscored"


def summarize(manifest_path):
    digest, samples = load_samples(Path(manifest_path))
    grouped = defaultdict(list)
    for sample in samples:
        grouped[json.dumps(sample["condition"], sort_keys=True)].append(sample)
    groups = []
    for key, rows in sorted(grouped.items()):
        scored = [r for r in rows if r["correct"] is not None]
        event_coverage = {}
        for stage in STAGES:
            event_coverage[stage] = {
                field: sum(r["event_timing_coverage"][stage][field] for r in rows)
                for field in ("observed_events", "events")}
        timing = {}
        for stage in (*STAGES, *REQUEST_STAGES):
            # Completed requests and interrupted work have distinct distributions.
            timing[stage] = {
                status: distribution([r["timings"][stage] for r in rows
                                      if r["failed"] == failed and r["timings"][stage] is not None])
                for status, failed in (("success", False), ("failed", True))}
        statuses = Counter()
        for row in rows:
            statuses.update(row["recall_statuses"])
        peaks = [r["observed_peak_positions"] for r in rows
                 if r["observed_peak_positions"] is not None]
        groups.append({
            "condition": json.loads(key), "requests": len(rows),
            "distinct_tasks": len({r["task_id"] for r in rows}),
            "failed": sum(r["failed"] for r in rows), "scored": len(scored),
            "correct": sum(r["correct"] is True for r in scored),
            "outcomes": dict(Counter(outcome(r) for r in rows)),
            "elapsed_ms": {
                status: distribution([r["elapsed_ms"] for r in rows
                                      if r["failed"] == failed and r["elapsed_ms"] is not None])
                for status, failed in (("success", False), ("failed", True))},
            "timings_ms": timing, "event_timing_coverage": event_coverage,
            "recall_statuses": dict(statuses),
            "recall_events": distribution([r["recall_events"] for r in rows
                                            if r["recall_events"] is not None]),
            "observed_peak_positions": distribution(peaks),
            "position_coverage": dict(Counter(r["position_coverage"] for r in rows)),
            "native_metrics_coverage": sum(r["native_memory_metrics"] is not None for r in rows),
            "native_metrics": {
                name: distribution([r["native_memory_metrics"][name] for r in rows
                                    if r["native_memory_metrics"] is not None and r["native_memory_metrics"].get(name) is not None])
                for name in ("source_reads", "scheduled_skips", "exhausted_steps", "addressing_attempts", "addressing_failures",
                             "peak_active_records", "peak_active_encoded_bytes", "peak_active_recurrent_bytes", "native_replays", "replay_wall_ns")},
            "observed_position_budget_violations": sum(
                p > json.loads(key)["position_budget"] for p in peaks),
            "counts": {name: distribution([r["counts"][name] for r in rows
                                            if r["counts"][name] is not None])
                       for name in ("native_reads", "memory_encoding_passes")},
        })
    return {"schema": "native-addressing-audit-v1", "manifest_sha256": digest,
            "measurement_notes": [
                "Conditions and failure/success timings remain separate.",
                "Missing measurements are unknown; partial event sums are withheld.",
                "Timing stages can overlap and must not be added.",
                "CPU bank application is not completed GPU attention time.",
                "Position coverage distinguishes post-recall working sets from legacy encoding events.",
                "Encoded bytes are logical K/V across native layers, not physical device residency.",
                "Addressing wall time includes bank preparation and host readback; stages overlap.",
                "Quality labels are supplied externally; this tool does not score answers.",
                "Repeated tasks are not independent knowledge samples."],
            "groups": groups, "samples": samples}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, help="new report file; existing files are refused")
    args = parser.parse_args()
    try:
        report = json.dumps(summarize(args.manifest), indent=2, allow_nan=False) + "\n"
        if args.output:
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as handle:
                handle.write(report)
        else:
            print(report, end="")
    except (ValueError, TypeError, OSError) as error:
        parser.exit(2, f"audit failed: {error}\n")


if __name__ == "__main__":
    main()
