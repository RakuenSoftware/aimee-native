#!/usr/bin/env bash
# Build the private native service against an explicit Aimee checkout.
# These binaries are staging inputs, not a complete self-hosted release.
set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "usage: $0 AIMEE_CHECKOUT OUTPUT_DIRECTORY" >&2
    exit 2
fi

aimee_checkout=$(realpath "$1")
output_dir=$(realpath -m "$2")
private_checkout=$(git -C "$(dirname "$0")/../.." rev-parse --show-toplevel)
go_bin=${GO_BIN:-go}

test -f "$aimee_checkout/server-go/go.mod" || {
    echo "Aimee checkout with server-go/go.mod required" >&2
    exit 2
}
test -f "$private_checkout/go.mod" || {
    echo "aimee-native go.mod required" >&2
    exit 2
}
for checkout in "$private_checkout" "$aimee_checkout"; do
    if [ -n "$(git -C "$checkout" status --porcelain --untracked-files=all)" ]; then
        echo "clean source checkout required: $checkout" >&2
        exit 2
    fi
done
mkdir -p "$output_dir"
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT

GOWORK="$scratch/go.work" "$go_bin" work init "$private_checkout" "$aimee_checkout/server-go"
for name in aimee-native-delivery aimee-memory-publish aimee-memory-read aimee-memory-image; do
    (cd "$private_checkout" && GOWORK="$scratch/go.work" "$go_bin" build \
        -trimpath -buildvcs=false -ldflags=-buildid= \
        -o "$output_dir/$name" "./cmd/$name")
done

{
    printf 'aimee-native=%s\n' "$(git -C "$private_checkout" rev-parse HEAD)"
    printf 'aimee=%s\n' "$(git -C "$aimee_checkout" rev-parse HEAD)"
    (cd "$output_dir" && sha256sum aimee-native-delivery aimee-memory-publish \
        aimee-memory-read aimee-memory-image)
} > "$output_dir/SOURCE-AND-SHA256SUMS"

echo "Built native server components in $output_dir"
