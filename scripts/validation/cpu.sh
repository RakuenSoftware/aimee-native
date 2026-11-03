#!/bin/bash
# Complete source-level CPU validation. No server deployment or model downloads.
set -euo pipefail
cd "$(dirname "$0")/../.."
python=${PYTHON_BIN:-python3}
go_bin=${GO_BIN:-go}
"$python" scripts/validation/docs.py
mkdir -p .local/bin
cargo test --locked --no-default-features
cargo build --locked --no-default-features --bin aimee-native
cargo test --manifest-path distribution/launcher/Cargo.toml --locked --features model-plugin-client
cargo build --manifest-path distribution/launcher/Cargo.toml --locked --features model-plugin-client --bins
"$go_bin" test -race ./...
for name in aimee-memory-image aimee-memory-publish aimee-memory-read aimee-memory-bus-probe aimee-kb-seed aimee-native-delivery; do
  "$go_bin" build -o ".local/bin/$name" "./cmd/$name"
done
"$go_bin" build -o .local/bin/aimee-issue-fixture ./benchmarks/local_memory
export AIMEE_IMAGE_READER="$PWD/.local/bin/aimee-memory-image"
export AIMEE_FIXTURE_ISSUER="$PWD/.local/bin/aimee-issue-fixture"
export RUST_QWEN="$PWD/target/debug/aimee-native"
"$python" -m unittest discover -s integrations/qwen_aimee -v
"$python" -m unittest discover -s distribution/release -p 'test_*.py' -v
PYTHONPATH=distribution/vllm "$python" -m unittest discover -s distribution/vllm/tests -p test_cli.py -v
"$python" distribution/launcher/tests/test_connect_aimee_tls.py \
  "$PWD/distribution/launcher/target/debug/aimee-native"
