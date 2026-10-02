#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
llama=${1:?Patched llama.cpp checkout}
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT HUP INT TERM
c++ -std=c++17 -fPIC -shared -I"$llama/include" -I"$llama/ggml/include" -I"$repo/distribution/llama.cpp" "$repo/distribution/tests/provider-fixture.cpp" -o "$stage/fixture.so"
c++ -std=c++17 -I"$llama/include" -I"$llama/ggml/include" -I"$repo/distribution/llama.cpp" "$repo/distribution/llama.cpp/provider.cpp" "$repo/distribution/tests/provider-test.cpp" -ldl -o "$stage/test"
"$stage/test" "$stage/fixture.so"
echo 'Provider loading, separate sessions, activation failure and absent library: passed'
