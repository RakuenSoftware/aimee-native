#!/usr/bin/env python3
"""Stage, sign and locally verify the tested 0.2.2 private-preview wheel.

This does not copy anything to the release origin's web directory. The stage
is created only after the model, option and live-revision gates have passed.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def read(path):
    return json.loads(path.read_text())


parser = argparse.ArgumentParser()
parser.add_argument("--workdir", type=Path, required=True)
parser.add_argument("--stage", type=Path, required=True)
parser.add_argument("--origin", type=Path, default=Path("/opt/aimee-native-release"))
args = parser.parse_args()
work = args.workdir

audit = read(work / "wheel-audit-final.json")
wheel = work / "release-final" / "aimee_vllm-0.2.2-1-cp312-cp312-linux_x86_64.whl"
require(audit["status"] == "passed" and audit["wheel"] == wheel.name,
        "final wheel audit missing or for a different wheel")
require(hashlib.sha256(wheel.read_bytes()).hexdigest() == audit["sha256"],
        "wheel differs from audited candidate")
require(wheel.stat().st_size == audit["bytes"], "wheel size differs from audit")

models = {}
for name in ("gemma12", "gemma26", "qwen27"):
    probe = read(work / f"{name}-amd-probe-r5.json")
    matrix = read(work / f"{name}-amd-matrix-r5.json")
    require(probe["status"] == "passed" and probe["consumer_from_wheel"],
            f"{name}: installed-wheel probe failed")
    require(len(probe["answers"]) == 4 and all(row["passed"] for row in probe["answers"]),
            f"{name}: native probe answers failed")
    require(probe["empty_first"]["passed"] and
            all(row["passed"] for row in probe["interleaved_tasks"]),
            f"{name}: empty control failed")
    for arm in ("native", "empty"):
        group = matrix["groups"][arm]
        require(group["correct"] == group["requests"] == 8 and
                group["admission_retries"] == 0,
                f"{name}: {arm} four-client matrix failed")
    models[name] = {"native_probe": 4, "native_matrix": 8, "empty_matrix": 8}

cuda_matrix = read(work / "gemma12-5080-final-v2-combined.json")
for arm in ("native", "empty"):
    group = cuda_matrix["groups"][arm]
    require(group["correct"] == group["requests"] == 8 and
            group["admission_retries"] == 0,
            f"RTX 5080: {arm} V2 combined matrix failed")

options = {}
for name in ("eager_v1", "prefix_v1", "async_v1", "piecewise_v1",
             "eager_v2", "combined_v2"):
    result = read(work / "perf-amd-r1" / f"{name}.summary.json")
    require(result["status"] == "passed", f"{name}: option run failed")
    for arm in ("native", "empty"):
        score = result["summary"][arm]
        require(score["correct"] == score["total"] == 6,
                f"{name}: {arm} option answers failed")
    options[name] = {"native": 6, "empty": 6}

revision = read(work / "live-revision-amd-r1.json")
require(revision["status"] == "passed" and revision["overlap"],
        "live publication change was not observed during an old stream")
require(revision["after_first_publication"]["digest"] !=
        revision["after_replacement"]["digest"], "catalogue digest did not change")
require(revision["followup"]["correct"] == revision["followup"]["total"] == 30,
        "repeated live selection failed")

public_hex = (args.origin / "release-public.hex").read_text().strip()
require(public_hex == "5d14ca247841adcc1130a4d95b82ead12ba699c03f2ba45f2f47524abde0c6c2",
        "unexpected release signing identity")
args.stage.mkdir(parents=True, exist_ok=False)
staged_wheel = args.stage / wheel.name
shutil.copyfile(wheel, staged_wheel)
base = "https://192.168.0.126:8445/plugins/portable/0.2.2/"
manifest = {
    "version": "0.2.2", "wheel": wheel.name, "url": base + wheel.name,
    "sha256": audit["sha256"], "bytes": audit["bytes"],
    "compatibility": audit["compatibility"],
    "scope": "Controlled standalone vLLM plugin preview with revision-safe prefix caching, optional async scheduling, and optional piecewise compilation; user supplies supported vLLM and model files.",
    "models": models, "option_validation": options,
    "rtx_5080_v2_combined": {"native": 8, "empty": 8},
    "live_revision_overlap": True, "live_selection_followups": 30,
    "executed_gpu_architectures": ["gfx1100", "sm120"],
    "native_library_sha256": audit["native_library_sha256"],
    "private_encoder_source_included": False, "runtime_image_included": False,
}
manifest_path = args.stage / "manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
with tempfile.TemporaryDirectory() as temp:
    public_der = Path(temp) / "public.der"
    public_der.write_bytes(bytes.fromhex("302a300506032b6570032100" + public_hex))
    for path in (staged_wheel, manifest_path):
        signature = path.with_name(path.name + ".sig")
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey",
                        str(args.origin / "private" / "release.key"), "-rawin",
                        "-in", str(path), "-out", str(signature)], check=True,
                       capture_output=True)
        subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin",
                        "-keyform", "DER", "-inkey", str(public_der), "-rawin",
                        "-in", str(path), "-sigfile", str(signature)], check=True,
                       capture_output=True)
record = {"status": "staged_and_signature_verified", "published": False,
          "stage": str(args.stage), "manifest_sha256":
          hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
          "wheel_sha256": audit["sha256"]}
(args.stage / "staging.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record))
