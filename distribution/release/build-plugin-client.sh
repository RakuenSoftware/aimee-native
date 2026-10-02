#!/bin/sh
# Private portable build. Users install the finished wheel, not this toolchain.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
: "${AIMEE_PLUGIN_OUTPUT:?empty output directory required}"
: "${AIMEE_PLUGIN_NOTICES:?consumer notices required}"
: "${AIMEE_GGUF_SOURCE:?upstream GGUF wheel containing the existing Triton fallback required}"
: "${AIMEE_PLUGIN_DOWNLOAD_BASE:?controlled HTTPS dependency download base required}"
python3 "$repo/distribution/release/build-portable-plugin.py" \
 --output "$AIMEE_PLUGIN_OUTPUT" --notices "$AIMEE_PLUGIN_NOTICES" \
 --gguf-source "$AIMEE_GGUF_SOURCE" --download-base "$AIMEE_PLUGIN_DOWNLOAD_BASE"
