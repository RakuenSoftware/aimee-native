"""Freeze a synthetic corpus and query-form splits before training."""
import argparse
import hashlib
import json
from pathlib import Path
import random


SCHEMA = [
    ("stable_fact", "beacon color", ["amber", "violet", "teal", "silver", "crimson"]),
    ("preference", "preferred drink", ["oolong", "espresso", "lemonade", "cocoa", "water"]),
    ("entity_property", "home city", ["Oslo", "Lima", "Kyoto", "Dakar", "Perth"]),
    ("project_fact", "release codename", ["Willow", "Kestrel", "Quartz", "Harbor", "Cobalt"]),
    ("technical_configuration", "RAM capacity", ["32 GB", "64 GB", "96 GB", "128 GB", "256 GB"]),
    ("procedure", "required first maintenance step", ["isolate power", "close valves", "save logs", "drain coolant", "verify backup"]),
]


def build(count=1000, seed=4817):
    if count < 12:
        raise ValueError("at least 12 memories required")
    rng = random.Random(seed)
    memories, train, heldout = [], [], []
    for i in range(count):
        category, attribute, choices = SCHEMA[i % len(SCHEMA)]
        entity = "unit-" + rng.randbytes(5).hex()
        value = rng.choice(choices)
        mid = 100000 + i
        memories.append(dict(memory_id=mid, category=category, entity=entity,
                             content=f"The {attribute} of {entity} is {value}.",
                             answer=value, active=True))
        base = dict(memory_ids=[mid], answer=value, category=category)
        train.extend([dict(base, id=f"train-{i}-{j}", query=query) for j, query in enumerate([
            f"What is the {attribute} of {entity}?",
            f"Give {entity}'s {attribute}."])])
        heldout.append(dict(base, id=f"heldout-{i}",
                            query=f"For {entity}, which value is recorded under {attribute}?"))
    # Composition needs two independently bound answers, not an answer label
    # that could be supplied by either fact alone.
    for i in range(0, count - 1, 10):
        a, b = memories[i:i+2]
        qa, qb = SCHEMA[i % 6][1], SCHEMA[(i+1) % 6][1]
        base = dict(memory_ids=[a["memory_id"], b["memory_id"]],
                    answer=a["answer"] + "; " + b["answer"], category="composition")
        train.append(dict(base, id=f"train-compose-{i}", query=
            f"Give the {qa} of {a['entity']}, then the {qb} of {b['entity']}. Separate with a semicolon."))
        heldout.append(dict(base, id=f"heldout-compose-{i}", query=
            f"Report these in order: {a['entity']} ({qa}); {b['entity']} ({qb}). Use a semicolon between values."))
    return dict(version=1, seed=seed, scope="synthetic.p0", generation=1,
                memories=memories, train=train, heldout=heldout,
                limitations=["Held-out query forms, not held-out memories.",
                             "Limited answer vocabulary: binding and absent-bank controls are essential.",
                             "No live Aimee memory or production governance policy."])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--count", type=int, default=1000)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    data = build(args.count)
    hashes = {}
    for name, payload in [("memories.json", {k:v for k,v in data.items() if k not in ("train", "heldout")}),
                          ("train.json", data["train"]), ("heldout.json", data["heldout"])]:
        raw = (json.dumps(payload, indent=2) + "\n").encode()
        (args.out / name).write_bytes(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    (args.out / "sha256.json").write_text(json.dumps(hashes, indent=2) + "\n")
    print(json.dumps(dict(memories=len(data["memories"]), train=len(data["train"]), heldout=len(data["heldout"]))))


if __name__ == "__main__":
    main()
