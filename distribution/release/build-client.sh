#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
: "${LIBTORCH:?Current bridge requires LibTorch; this is not a ggml build}"
export CXXFLAGS="${CXXFLAGS:-} -ffile-prefix-map=$repo=/aimee-native -ffile-prefix-map=$LIBTORCH=/aimee-deps/torch"
export RUSTFLAGS="${RUSTFLAGS:-} --remap-path-prefix=$repo=/aimee-native -C link-arg=-Wl,--build-id=none -C link-arg=-Wl,--exclude-libs,ALL -C link-arg=-Wl,--gc-sections"
cd "$repo"
# --lib deliberately excludes the research server and benchmark binaries.
cargo build --locked --release --lib --no-default-features --features native-client
python3 distribution/release/audit-client.py "${CARGO_TARGET_DIR:-target}/release/libaimee_native.so"
