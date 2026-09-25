#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
export RUSTFLAGS="${RUSTFLAGS:-} --remap-path-prefix=$repo=/aimee-native"
cd "$repo"
cargo build --locked --release --lib --no-default-features --features vllm-client
python3 distribution/release/audit-client.py "${CARGO_TARGET_DIR:-target}/release/libaimee_qwen.so" --vllm
