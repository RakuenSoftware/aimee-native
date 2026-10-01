#!/usr/bin/env python3
"""Sign a public GitHub Release asset set after public-wheel GPU probes pass.

Staging is offline and non-public. No files are written to the GitHub repo or
the controlled download origin by this script.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZipFile


TAG = "native-memory-v0.2.2"
WHEEL = "aimee_vllm-0.2.2-2-cp312-cp312-linux_x86_64.whl"
GGUF = "vllm_gguf_plugin-0.0.5+triton-py3-none-any.whl"
PUBLIC_KEY = "5d14ca247841adcc1130a4d95b82ead12ba699c03f2ba45f2f47524abde0c6c2"
BASE = f"https://github.com/RakuenSoftware/aimee/releases/download/{TAG}/"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--origin", type=Path, default=Path("/opt/aimee-native-release"))
    args = parser.parse_args()
    work = args.workdir
    public_wheel = work / WHEEL
    dependency = work / GGUF
    retarget = json.loads((work / "retarget-report.json").read_text())
    audit = json.loads((work / "public-wheel-audit.json").read_text())
    require(retarget["status"] == "passed" and retarget["runtime_members_identical"],
            "public wheel runtime does not match reviewed private candidate")
    require(retarget["input_sha256"] ==
            "ff069f26ff20316e91576e3f901275b41e74599b5c2b73b5f307eb297fa9d46e",
            "unreviewed input wheel")
    require(audit["status"] == "passed" and audit["wheel"] == WHEEL,
            "public wheel packaging audit failed")
    require(audit["sha256"] == retarget["public_wheel_sha256"] == sha(public_wheel),
            "public wheel digest mismatch")
    require(retarget["gguf_dependency_sha256"] == sha(dependency),
            "GGUF dependency digest mismatch")
    require(retarget["gguf_dependency_url"] == BASE + GGUF,
            "GGUF URL does not target the intended public release")
    with ZipFile(public_wheel) as archive:
        require(not any(b"192.168." in archive.read(name)
                        for name in archive.namelist()),
                "private network address remains in public wheel")

    for name in ("gemma12-amd-public-build2-install.json",
                 "gemma12-5080-public-build2-install.json"):
        installed = json.loads((work / name).read_text())
        require(installed == {"status": "passed", "wheel": WHEEL,
                              "sha256": audit["sha256"]},
                f"tested environment did not install the public wheel: {name}")

    for name in ("gemma12-amd-public-build2-probe-r2.json",
                 "gemma12-5080-public-build2-probe.json"):
        result = json.loads((work / name).read_text())
        require(result["status"] == "passed" and result["consumer_from_wheel"],
                f"installed public-wheel probe failed: {name}")
        require(len(result["answers"]) == 4 and all(x["passed"] for x in result["answers"]),
                f"native answers failed: {name}")
        require(result["empty_first"]["passed"] and
                len(result["interleaved_tasks"]) == 4 and
                all(x["passed"] for x in result["interleaved_tasks"]),
                f"empty controls failed: {name}")

    require((args.origin / "release-public.hex").read_text().strip() == PUBLIC_KEY,
            "unexpected signing identity")
    args.stage.mkdir(parents=True, exist_ok=False)
    for source in (public_wheel, dependency):
        shutil.copyfile(source, args.stage / source.name)
    manifest = {
        "release": TAG,
        "package": "aimee-vllm",
        "version": "0.2.2",
        "scope": "Controlled public preview: standalone vLLM plugin and Aimee connection client. An enrolled Aimee account and authorized publication are required for native memory.",
        "assets": {
            WHEEL: {"url": BASE + WHEEL, "sha256": sha(public_wheel),
                    "bytes": public_wheel.stat().st_size},
            GGUF: {"url": BASE + GGUF, "sha256": sha(dependency),
                   "bytes": dependency.stat().st_size},
        },
        "public_key_ed25519_hex": PUBLIC_KEY,
        "compatibility": audit["compatibility"],
        "tested_models": {"Qwen3.8 27B": "V1 on gfx1100",
                          "Gemma 4 12B": "V2 on gfx1100 and sm120",
                          "Gemma 4 26B": "V2 on gfx1100"},
        "compiled_runtime_identical_to_reviewed_private_wheel": True,
        "private_encoder_source_included": False,
        "model_weights_included": False,
        "vllm_runtime_included": False,
    }
    manifest_path = args.stage / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    sums = args.stage / "SHA256SUMS"
    files = [args.stage / WHEEL, args.stage / GGUF, manifest_path]
    sums.write_text("".join(f"{sha(path)}  {path.name}\n" for path in files))
    files.append(sums)
    with tempfile.TemporaryDirectory(prefix="aimee-public-stage-") as temporary:
        public_der = Path(temporary) / "release-public.der"
        public_der.write_bytes(bytes.fromhex("302a300506032b6570032100" + PUBLIC_KEY))
        for path in files:
            signature = path.with_name(path.name + ".sig")
            subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey",
                            str(args.origin / "private/release.key"), "-rawin",
                            "-in", str(path), "-out", str(signature)],
                           capture_output=True, check=True)
            subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin",
                            "-keyform", "DER", "-inkey", str(public_der),
                            "-rawin", "-in", str(path), "-sigfile", str(signature)],
                           capture_output=True, check=True)
    record = {"status": "staged_and_signature_verified", "published": False,
              "release": TAG, "wheel_sha256": sha(public_wheel),
              "manifest_sha256": sha(manifest_path), "asset_count": len(files)}
    (args.stage / "staging.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))


if __name__ == "__main__":
    main()
