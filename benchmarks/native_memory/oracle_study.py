#!/usr/bin/env python3
"""Execute the predeclared oracle study serially with atomic progress records."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--placement", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    plan_path = source / "oracle-study-plan.json"
    plan = json.loads(plan_path.read_text())
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "plan.json").write_bytes(plan_path.read_bytes())
    started = time.monotonic()
    state = dict(started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(), completed=[])

    def publish(phase, **fields):
        state.update(phase=phase, elapsed_seconds=time.monotonic()-started, **fields)
        path = args.out / "study-state.tmp"
        path.write_text(json.dumps(state, indent=2)+"\n")
        path.replace(args.out / "study-state.json")
        print(json.dumps(state), flush=True)

    try:
        for run in plan["runs"]:
            out = args.out / run["name"]
            command = [sys.executable, str(source / "pilot.py"), "--model", args.model,
                       "--fixtures", str(args.fixtures), "--placement", str(args.placement),
                       "--out", str(out), "--steps", str(plan["steps_each"]),
                       "--bank-policy", plan["bank_policy"], "--adapter-dtype", run["adapter_dtype"],
                       "--lr", str(run["lr"])]
            publish("running", active_run=run["name"], command=command)
            subprocess.run(command, check=True)
            report = json.loads((out / "evaluation" / "summary.json").read_text())
            state["completed"].append(dict(name=run["name"], summary=report))
        publish("complete", active_run=None)
    except BaseException as error:
        publish("failed", error=repr(error))
        raise


if __name__ == "__main__":
    main()
