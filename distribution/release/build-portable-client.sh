#!/bin/sh
# Private CPU-only build. No ROCm/CUDA toolkit, GPU target or LibTorch linkage.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
export PYTHON_INCLUDE="${PYTHON_INCLUDE:-$(python3 -c 'import sysconfig;print(sysconfig.get_path("include"))')}"
export RUSTFLAGS="${RUSTFLAGS:-} --remap-path-prefix=$repo=/aimee-native -C link-arg=-Wl,--build-id=none -C link-arg=-Wl,--exclude-libs,ALL -C link-arg=-Wl,--gc-sections"
export CXXFLAGS="${CXXFLAGS:-} -ffile-prefix-map=$repo=/aimee-native -ffile-prefix-map=$PYTHON_INCLUDE=/runtime/python"
cd "$repo"
cargo build --locked --release --lib --no-default-features --features vllm-portable
python3 distribution/release/harden-elf.py "${CARGO_TARGET_DIR:-target}/release/libaimee_qwen.so"
python3 distribution/release/audit-client.py "${CARGO_TARGET_DIR:-target}/release/libaimee_qwen.so" --vllm --runtime

cargo build --manifest-path distribution/launcher/Cargo.toml --locked --release
python3 distribution/release/harden-elf.py "${CARGO_TARGET_DIR:-target}/release/aimee-native"
