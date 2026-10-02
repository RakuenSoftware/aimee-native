#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
export RUSTFLAGS="${RUSTFLAGS:-} --remap-path-prefix=$repo=/aimee-native"
# Build against the exact deployed ATen and CPython ABI, not a second runtime.
: "${LIBTORCH:?Set LIBTORCH to the pinned runtime torch package}"
: "${AIMEE_CODEC_OBJECT:?Set AIMEE_CODEC_OBJECT to the pinned compiled decoder object}"
: "${HIP_LIB_DIR:?Set HIP_LIB_DIR to the pinned HIP runtime library directory}"
: "${PYTHON_INCLUDE:?Set PYTHON_INCLUDE to the pinned runtime Python headers}"
export CXXFLAGS="${CXXFLAGS:-} -ffile-prefix-map=$repo=/aimee-native -ffile-prefix-map=$LIBTORCH=/runtime/torch -ffile-prefix-map=$PYTHON_INCLUDE=/runtime/python"
cd "$repo"
cargo build --locked --release --lib --no-default-features --features vllm-runtime
python3 distribution/release/audit-client.py "${CARGO_TARGET_DIR:-target}/release/libaimee_qwen.so" --vllm --runtime
