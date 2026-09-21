#!/usr/bin/env python3
"""Run a fixed-budget P0 pilot and evaluate automatically; persist job status.

Launch from an immutable source snapshot in a managed service. This does not
promote artifacts or make any Aimee/serving changes.
"""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--placement", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=2100)
    parser.add_argument("--bank-policy", choices=["distractors", "oracle"], default="distractors")
    parser.add_argument("--adapter-dtype", choices=["base", "float32"], default="base")
    parser.add_argument("--lr", type=float, default=0.001)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    recorded = datetime.datetime.now(datetime.timezone.utc).isoformat()
    commands = []

    def status(phase, **extra):
        data = dict(phase=phase, started_at=recorded, elapsed_seconds=time.monotonic()-started,
                    commands=commands, **extra)
        temporary = args.out / "job-state.tmp"
        temporary.write_text(json.dumps(data, indent=2)+"\n")
        temporary.replace(args.out / "job-state.json")
        print(json.dumps(data), flush=True)

    shared = ["--model", args.model, "--fixtures", str(args.fixtures),
              "--placement", str(args.placement), "--base-quantization", "int8_per_row_v1",
              "--dtype", "bfloat16", "--value-width", "2048", "--attention-width", "256",
              "--k", "16", "--after-block", "1", "--seed", "4817", "--lr", str(args.lr),
              "--bank-policy", args.bank_policy, "--adapter-dtype", args.adapter_dtype]
    runner = [sys.executable, str(Path(__file__).with_name("run_p0.py"))]
    try:
        commands.append(runner + ["train", *shared, "--steps", str(args.steps), "--out", str(args.out / "train")])
        status("training")
        subprocess.run(commands[-1], check=True)
        commands.append(runner + ["evaluate", *shared, "--checkpoint", str(args.out / "train" / "adapter.pt"),
                                 "--out", str(args.out / "evaluation")])
        status("evaluating")
        subprocess.run(commands[-1], check=True)
        report = json.loads((args.out / "evaluation" / "summary.json").read_text())
        status("complete", summary=report)
    except BaseException as error:
        status("failed", error=repr(error))
        raise


if __name__ == "__main__":
    main()
