#!/bin/sh
set -eu
: "${AIMEE_RELEASE_PUBLIC_KEY:?Set the public verification key, not the signing key}"
: "${AIMEE_RELEASE_URL:?Set the HTTPS release origin}"
# Optional AIMEE_RELEASE_CA_PEM contains the public origin/registry CA, never a
# private key. Cargo embeds it for verified private-PKI downloads and OCI pulls.
case "$AIMEE_RELEASE_URL" in https://*) ;; *) exit 1;; esac
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
export RUSTFLAGS="${RUSTFLAGS:-} --remap-path-prefix=$repo=/aimee-native -C link-arg=-Wl,--build-id=none -C link-arg=-Wl,--exclude-libs,ALL -C link-arg=-Wl,--gc-sections"
exec cargo build --locked --release --manifest-path "$repo/distribution/launcher/Cargo.toml"
