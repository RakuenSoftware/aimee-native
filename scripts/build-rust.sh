#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${LIBTORCH:?Set LIBTORCH to the native libtorch distribution directory}"
if [[ "${AIMEE_TORCH_214_COMPAT:-0}" == 1 ]]; then
    # Explicit research compatibility path. tch 0.26 normally targets 2.13.
    export LIBTORCH_BYPASS_VERSION_CHECK=1
    export CXXFLAGS="${CXXFLAGS:-} -std=c++20 -g0 -include $PWD/native/torch_214_compat.h"
fi
cargo build --release --locked "$@"
