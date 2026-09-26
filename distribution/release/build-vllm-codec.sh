#!/bin/sh
# Run inside the pinned ROCm runtime image; do not compile against host ROCm.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
: "${AIMEE_CODEC_OBJECT:?Set output object path}"
: "${AIMEE_GPU_ARCH:?Set the certified architecture, e.g. gfx1100}"
"${HIPCC:-/opt/rocm/bin/hipcc}" -O3 -std=c++17 -fPIC -fvisibility=hidden \
  --offload-arch="$AIMEE_GPU_ARCH" -ffile-prefix-map="$repo"=/aimee-native \
  -c "$repo/native/vllm_codec.hip" -o "$AIMEE_CODEC_OBJECT"
