#!/bin/sh
set -eu
: "${AIMEE_RELEASE_PUBLIC_KEY:?Set the public verification key, not the signing key}"
: "${AIMEE_RELEASE_URL:?Set the HTTPS release origin}"
case "$AIMEE_RELEASE_URL" in https://*) ;; *) exit 1;; esac
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
export RUSTFLAGS="${RUSTFLAGS:-} --remap-path-prefix=$repo=/aimee-native"
exec cargo build --locked --release --manifest-path "$repo/distribution/launcher/Cargo.toml"
