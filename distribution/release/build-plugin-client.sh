#!/bin/sh
# Private build in the supported vLLM ABI environment; users install the wheel.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
: "${AIMEE_PLUGIN_MODULE_WHEEL:?compiled module wheel required}"
: "${AIMEE_PLUGIN_NATIVE_LIBRARY:?compiled Rust/ATen consumer required}"
: "${AIMEE_PLUGIN_KERNEL_BANK:?matched compiled kernel bank required}"
: "${AIMEE_PLUGIN_NOTICES:?consumer notices required}"
: "${AIMEE_GGUF_WHEEL_URL:?tested ROCm GGUF wheel URL required}"
: "${AIMEE_GGUF_WHEEL_SHA256:?tested GGUF wheel SHA-256 required}"
: "${AIMEE_PLUGIN_OUTPUT:?empty output directory required}"
export RUSTFLAGS="${RUSTFLAGS:-} --remap-path-prefix=$repo=/aimee-native"
cargo test --manifest-path "$repo/distribution/launcher/Cargo.toml" --locked --offline -- --test-threads=1
cargo build --manifest-path "$repo/distribution/launcher/Cargo.toml" --release --locked --offline
python3 "$repo/distribution/release/assemble-plugin-wheel.py" \
 --wheel "$AIMEE_PLUGIN_MODULE_WHEEL" \
 --launcher "${CARGO_TARGET_DIR:-$repo/distribution/launcher/target}/release/aimee-native" \
 --library "$AIMEE_PLUGIN_NATIVE_LIBRARY" --kernels "$AIMEE_PLUGIN_KERNEL_BANK" \
 --notices "$AIMEE_PLUGIN_NOTICES" --output "$AIMEE_PLUGIN_OUTPUT" \
 --gguf-wheel-url "$AIMEE_GGUF_WHEEL_URL" --gguf-wheel-sha256 "$AIMEE_GGUF_WHEEL_SHA256"
