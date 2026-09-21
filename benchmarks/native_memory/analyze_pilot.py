#!/usr/bin/env python3
"""Re-score pilot-001 without changing original results or importing PyTorch."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    training = [json.loads(line) for line in (args.pilot / "training.jsonl").read_text().splitlines()]
    evaluation = [json.loads(line) for line in (args.pilot / "evaluation.jsonl").read_text().splitlines()]
    norm = lambda text: [" ".join(part.casefold().split()) for part in text.split(";")]
    modes = sorted({row["mode"] for row in evaluation})
    accuracy = {}
    for mode in modes:
        rows = [r for r in evaluation if r["mode"] == mode]
        accuracy[mode] = dict(legacy_correct=sum(r["correct"] for r in rows),
                             value_correct=sum(r["terminated"] and norm(r["answer"]) == norm(r["expected"]) for r in rows),
                             total=len(rows))
    native = {r["id"]: r for r in evaluation if r["mode"] == "native"}
    wrong = {r["id"]: r for r in evaluation if r["mode"] == "native_distractors"}
    report = dict(original_results_unchanged=True, rescoring="ordered semicolon-delimited exact values",
        accuracy=accuracy, same_native_and_distractors=sum(r["answer"] == wrong[key]["answer"] for key, r in native.items()),
        native_answer_counts=dict(Counter(r["answer"] for r in native.values())),
        epoch_means=[dict(epoch=i//210+1, **{key: statistics.mean(r[key] for r in training[i:i+210])
                       for key in ["loss", "grad_norm", "value_grad_norm", "output_grad_norm"]})
                     for i in range(0, len(training), 210)])
    with args.out.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
