#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
checkout=${1:?Path to the pinned llama.cpp checkout}
expected=e85e15cf6d810cd1268498c2e5b657bb3ece47bc
actual=$(git -C "$checkout" rev-parse HEAD)
[ "$actual" = "$expected" ] || { echo 'llama.cpp revision mismatch' >&2; exit 1; }
git -C "$checkout" apply --check "$repo/native-attention.patch"
git -C "$checkout" apply "$repo/native-attention.patch"
