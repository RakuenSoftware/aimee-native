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

audit = read(work / "wheel-audit-lease-r1-ubuntu.json")
wheel = work / "release-lease-r1-ubuntu" / "aimee_vllm-0.2.2-1-cp312-cp312-linux_x86_64.whl"
require(audit["status"] == "passed" and audit["wheel"] == wheel.name,
        "final wheel audit missing or for a different wheel")
require(hashlib.sha256(wheel.read_bytes()).hexdigest() == audit["sha256"],
        "wheel differs from audited candidate")
require(wheel.stat().st_size == audit["bytes"], "wheel size differs from audit")

models = {}
for name in ("gemma12", "gemma26", "qwen27"):
    run = "r9b" if name == "gemma26" else "r9"
    probe = read(work / f"{name}-amd-probe-{run}.json")
    matrix = read(work / f"{name}-amd-matrix-{run}.json")
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
    models[name] = {"native_probe": 4, "native_matrix": 8,
                    "empty_matrix": 8, "runner": "V1" if name == "qwen27" else "V2"}

cuda_probe = read(work / "gemma12-5080-lease-r1-probe.json")
require(cuda_probe["status"] == "passed" and cuda_probe["consumer_from_wheel"],
        "RTX 5080: corrected-wheel probe failed")
require(len(cuda_probe["answers"]) == 4 and
        all(row["passed"] for row in cuda_probe["answers"]) and
        cuda_probe["empty_first"]["passed"] and
        all(row["passed"] for row in cuda_probe["interleaved_tasks"]),
        "RTX 5080: native or empty answer failed")

options = {}
for name in ("eager_v1", "prefix_v1", "async_v1", "piecewise_v1",
             "eager_v2", "combined_v2"):
    result = read(work / "perf-amd-lease-r1-r2" / f"{name}.summary.json")
    require(result["status"] == "passed", f"{name}: option run failed")
    for arm in ("native", "empty"):
        score = result["summary"][arm]
        require(score["correct"] == score["total"] == 6,
                f"{name}: {arm} option answers failed")
    options[name] = {"native": 6, "empty": 6}

revision = read(work / "live-revision-amd-lease-r1.json")
require(revision["status"] == "passed" and revision["overlap"],
        "live publication change was not observed during an old stream")
require(len(revision["replacement_attempts"]) == 1 and
        revision["replacement_attempts"][0]["status"] == 200,
        "live replacement required a failed admission and retry")
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
    "rtx_5080_v2_probe": {"native": 4, "empty": 5},
    "hybrid_model_runner": "V1; vLLM 0.30 hybrid V2 omits request slots and is rejected",
    "revision_request_started_during_old_stream": True,
    "revision_activation_drains_old_stream": True,
    "replacement_first_attempt_status": 200,
    "live_selection_followups": 30,
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
