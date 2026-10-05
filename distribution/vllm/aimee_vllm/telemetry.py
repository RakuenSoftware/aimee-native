"""Opt-in bounded host-stage counters; no tensors, queries or publication names."""
from contextlib import contextmanager
from time import perf_counter_ns

class Stages:
    def __init__(self, enabled=False):
        if type(enabled) is not bool:
            raise ValueError("native_stage_telemetry must be boolean")
        self.enabled = enabled
        self.rows = {}

    @contextmanager
    def measure(self, name):
        if not self.enabled:
            yield
            return
        start = perf_counter_ns()
        failed = False
        try:
            yield
        except BaseException:
            failed = True
            raise
        finally:
            key = name + ("_failed" if failed else "_success")
            row = self.rows.setdefault(key, {"count": 0, "total_ns": 0, "max_ns": 0})
            elapsed = perf_counter_ns() - start
            row["count"] += 1
            row["total_ns"] += elapsed
            row["max_ns"] = max(row["max_ns"], elapsed)

    def snapshot(self):
        return {"schema": "native-host-stages-v1", "enabled": self.enabled,
                "scope": "process-lifetime-host-wall; stages may overlap; not GPU execution",
                "stages": {k: dict(v) for k, v in self.rows.items()}}
