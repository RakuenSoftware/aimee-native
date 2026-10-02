#!/usr/bin/env python3
"""Review or publish the already signed 0.2.2 standalone plugin preview.

The default is read-only. --publish atomically adds an immutable versioned
directory to the controlled origin and verifies the delivered bytes over TLS.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import urllib.request
import uuid
from zipfile import ZipFile
from email.parser import BytesParser


VERSION = "0.2.2"
WHEEL_SHA256 = "ff069f26ff20316e91576e3f901275b41e74599b5c2b73b5f307eb297fa9d46e"
PUBLIC_KEY = "5d14ca247841adcc1130a4d95b82ead12ba699c03f2ba45f2f47524abde0c6c2"
BASE = f"https://192.168.0.126:8445/plugins/portable/{VERSION}/"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_signature(path, key):
    signature = path.with_name(path.name + ".sig")
    if len(signature.read_bytes()) != 64:
        raise ValueError(f"Incorrect signature length: {signature}")
    subprocess.run([
        "openssl", "pkeyutl", "-verify", "-pubin", "-keyform", "DER",
        "-inkey", str(key), "-rawin", "-in", str(path),
        "-sigfile", str(signature),
    ], check=True, capture_output=True)


def download(url, context, maximum):
    with urllib.request.urlopen(url, context=context, timeout=60) as response:
        data = response.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError(f"Oversize download: {url}")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--origin", type=Path, default=Path("/opt/aimee-native-release"))
    parser.add_argument("--publish", action="store_true",
                        help="write the immutable version directory and verify TLS delivery")
    args = parser.parse_args()

    stage = args.stage.resolve(strict=True)
    origin = args.origin.resolve(strict=True)
    record = json.loads((stage / "staging.json").read_text())
    manifest_path = stage / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    wheel = stage / manifest["wheel"]
    wheel_bytes = wheel.read_bytes()
    if record["status"] != "staged_and_signature_verified" or record["published"]:
        raise ValueError("Release stage is not an unpublished signed candidate")
    if manifest["version"] != VERSION or manifest["url"] != BASE + wheel.name:
        raise ValueError("Unexpected version or download URL")
    if not wheel.name.startswith(f"aimee_vllm-{VERSION}-"):
        raise ValueError("Unexpected wheel filename")
    if manifest["sha256"] != WHEEL_SHA256 or digest(wheel_bytes) != WHEEL_SHA256:
        raise ValueError("Wheel digest differs from approved candidate")
    if record["wheel_sha256"] != WHEEL_SHA256:
        raise ValueError("Stage record differs from approved candidate")
    if record["manifest_sha256"] != digest(manifest_bytes):
        raise ValueError("Staged manifest digest mismatch")
    if manifest["bytes"] != len(wheel_bytes):
        raise ValueError("Staged wheel byte count mismatch")
    if (origin / "release-public.hex").read_text().strip() != PUBLIC_KEY:
        raise ValueError("Unexpected signing identity")

    with tempfile.TemporaryDirectory(prefix="aimee-preview-review-") as temporary:
        key = Path(temporary) / "public.der"
        key.write_bytes(bytes.fromhex("302a300506032b6570032100" + PUBLIC_KEY))
        verify_signature(wheel, key)
        verify_signature(manifest_path, key)

        # The optional GGUF extra points at an immutable, hash-pinned wheel.
        with ZipFile(wheel) as archive:
            metadata_name = next(n for n in archive.namelist()
                                 if n.endswith(".dist-info/METADATA"))
            metadata = BytesParser().parsebytes(archive.read(metadata_name))
        dependencies = metadata.get_all("Requires-Dist", [])
        gguf = next((d for d in dependencies if "vllm-gguf-plugin @ " in d), None)
        if gguf is None or "#sha256=" not in gguf:
            raise ValueError("GGUF extra is not URL/hash pinned")
        gguf_url = gguf.split(" @ ", 1)[1].split("#sha256=", 1)[0]
        gguf_hash = gguf.split("#sha256=", 1)[1].split(" ", 1)[0]
        context = ssl.create_default_context(cafile=str(origin / "ca.pem"))
        if digest(download(gguf_url, context, 8 * 1024 * 1024)) != gguf_hash:
            raise ValueError("Pinned GGUF extra is unavailable or changed")

        if not args.publish:
            print(json.dumps({"status": "preflight_passed", "published": False,
                              "wheel_sha256": WHEEL_SHA256,
                              "manifest_sha256": digest(manifest_bytes),
                              "gguf_dependency_sha256": gguf_hash}))
            return

        parent = origin / "www/plugins/portable"
        destination = parent / VERSION
        if destination.exists():
            raise FileExistsError(f"Immutable version already exists: {destination}")
        temporary_destination = parent / ("." + VERSION + "-" + uuid.uuid4().hex)
        temporary_destination.mkdir(mode=0o755)
        try:
            for path in (wheel, wheel.with_name(wheel.name + ".sig"),
                         manifest_path, manifest_path.with_name("manifest.json.sig")):
                shutil.copyfile(path, temporary_destination / path.name)
            for path in (wheel, manifest_path):
                if (temporary_destination / path.name).read_bytes() != path.read_bytes():
                    raise ValueError(f"Copy changed {path.name}")
            temporary_destination.rename(destination)
        finally:
            if temporary_destination.exists():
                shutil.rmtree(temporary_destination)

        for path in (wheel, manifest_path):
            delivered = download(BASE + path.name, context, len(path.read_bytes()))
            if delivered != path.read_bytes():
                raise ValueError(f"TLS delivery differs for {path.name}")
            signature = download(BASE + path.name + ".sig", context, 64)
            if signature != path.with_name(path.name + ".sig").read_bytes():
                raise ValueError(f"TLS signature differs for {path.name}")
        print(json.dumps({"status": "published_and_verified", "url": manifest["url"],
                          "wheel_sha256": WHEEL_SHA256,
                          "manifest_sha256": digest(manifest_bytes)}))


if __name__ == "__main__":
    main()
