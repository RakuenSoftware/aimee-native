#!/usr/bin/env python3
"""Retarget only the optional GGUF download in a signed-preview wheel.

Produces a separate public build tag. All runtime members must remain byte-for-
byte identical; the input wheel and its private-release signatures are untouched.
"""

import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile


EXPECTED_INPUT = "ff069f26ff20316e91576e3f901275b41e74599b5c2b73b5f307eb297fa9d46e"
DEPENDENCY_HASH = "616360d726fbaf88c96ebbe9ec4a62fc69ba86cba591f1a8b609199ad5339246"
OLD_URL = "https://192.168.0.126:8445/plugins/portable/0.2.0/vllm_gguf_plugin-0.0.5+triton-py3-none-any.whl"
PUBLIC_URL = "https://github.com/RakuenSoftware/aimee/releases/download/native-memory-v0.2.2/vllm_gguf_plugin-0.0.5+triton-py3-none-any.whl"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    if sha256(args.input.read_bytes()) != EXPECTED_INPUT:
        raise ValueError("Input is not the release-reviewed wheel")
    if urlsplit(PUBLIC_URL).hostname != "github.com":
        raise ValueError("Unexpected public dependency host")
    expected_old = (OLD_URL + "#sha256=" + DEPENDENCY_HASH).encode()
    expected_new = (PUBLIC_URL + "#sha256=" + DEPENDENCY_HASH).encode()
    if args.output.exists():
        raise FileExistsError(args.output)
    if args.output.name != "aimee_vllm-0.2.2-2-cp312-cp312-linux_x86_64.whl":
        raise ValueError("Expected 0.2.2 public build tag 2")

    with ZipFile(args.input) as source:
        infos = source.infolist()
        files = {info.filename: source.read(info.filename) for info in infos}
        metadata = [n for n in files if n.endswith(".dist-info/METADATA")]
        record = [n for n in files if n.endswith(".dist-info/RECORD")]
        if len(metadata) != 1 or len(record) != 1:
            raise ValueError("Wheel needs exactly one metadata and RECORD member")
        name = metadata[0]
        if files[name].count(expected_old) != 1:
            raise ValueError("Expected one exact private GGUF dependency URL")
        files[name] = files[name].replace(expected_old, expected_new)

        output_record = io.StringIO()
        writer = csv.writer(output_record, lineterminator="\n")
        for filename in sorted(files):
            if filename == record[0]:
                writer.writerow([filename, "", ""])
            else:
                data = files[filename]
                encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
                writer.writerow([filename, "sha256=" + encoded, len(data)])
        files[record[0]] = output_record.getvalue().encode()

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(args.output, "x") as target:
            for info in infos:
                target.writestr(info, files[info.filename])

    with ZipFile(args.input) as old, ZipFile(args.output) as new:
        if old.namelist() != new.namelist():
            raise ValueError("Member list changed")
        changed = [n for n in old.namelist() if old.read(n) != new.read(n)]
        if sorted(changed) != sorted([metadata[0], record[0]]):
            raise ValueError(f"Unexpected changed members: {changed}")
    report = {
        "status": "passed", "input_sha256": EXPECTED_INPUT,
        "public_wheel": args.output.name,
        "public_wheel_sha256": sha256(args.output.read_bytes()),
        "public_wheel_bytes": args.output.stat().st_size,
        "changed_members": changed,
        "runtime_members_identical": True,
        "gguf_dependency_sha256": DEPENDENCY_HASH,
        "gguf_dependency_url": PUBLIC_URL,
        "dependency_url_live": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
