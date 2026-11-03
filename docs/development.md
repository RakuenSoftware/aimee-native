# Build and test Aimee Native

Use Rust 1.98.1 (pinned by `rust-toolchain.toml`), a C/C++ toolchain and Python
3.12 for plugin wheels. Cargo.lock and the launcher lockfile pin Rust dependencies.
Current enrolled serving communicates with Aimee v1.0.2 over HTTPS; a core source
checkout is unnecessary for end users.

## CPU source checks

The basic checks need no model weights, Torch or Aimee source:

```sh
cargo test --locked --no-default-features
cargo test --manifest-path distribution/launcher/Cargo.toml --locked --features model-plugin-client
python3 -m unittest discover -s distribution/release -p 'test_*.py' -v
```

For the complete CPU structural suite, install a compatible CPU Torch build
separately, plus `transformers==5.17.0` and safetensors. The recorded reference
uses `torch==2.14.0` from PyTorch's CPU index. These are the tiny-Qwen regression
dependencies; they are not the GPU vLLM serving environment or its pinned Torch
version. Use a disposable Python environment.

The Go research helpers require Go 1.26.7 and a source checkout containing the
historical Aimee pin. Prepare the ignored dependency extraction without changing
that checkout, then run the suite:

```sh
python3 scripts/prepare-research-dependency.py --source-checkout ../aimee
bash scripts/validation/cpu.sh
```

The preparation script reads the exact commit from
[the historical pin](../dependencies/aimee-source.json), extracts only its
`server-go` tree into `.local/aimee-research-ad3585ac`, and records the commit.
It is idempotent and rejects a preexisting directory without a matching marker.
`go.mod` points to that isolated dependency. A modern sibling checkout can remain
on its current branch. If the historical commit is absent, fetch it through your
existing repository access; do not replace the dependency with unscoped source
exports or copied policy code. Do not manually edit archived pins or evidence.

`cpu.sh` runs Rust runtime and launcher tests; builds all six Go commands and the
fixture issuer; runs Go race tests, the full Python adapter suite, packaging
contracts and a disposable mTLS client/broker test. It exports both Go helpers and
the renamed Rust executable so authorization tests do not silently skip their
compiled paths. `GO_BIN` and `PYTHON_BIN` can select installed tools. Build output
remains under ignored `.local` and `target` directories.

The source bridge's CPU suite additionally needs Triton 3.7.1 and the portable
Rust library. It runs test modules in separate processes to isolate framework
fixtures, and records explicit exclusions for the installed vLLM/GGUF tests:

```sh
export PYTHON_INCLUDE="$(python3 -c 'import sysconfig; print(sysconfig.get_path("include"))')"
cargo build --locked --lib --no-default-features --features vllm-portable
python3 scripts/validation/bridge-cpu.py \
  --library target/debug/libaimee_native.so --output .local/bridge-cpu.json
```

The real GPU attention test and the upstream vLLM request-schema test retain
explicit skips when their dependencies are absent. Run the complete
`distribution/vllm/tests` suite in the qualified upstream vLLM/GGUF/GPU environment
before release; fixture-based CPU checks do not replace it. With the complete
GPU environment and an unbound portable development library, run:

```sh
python3 scripts/validation/bridge-gpu.py \
  --library target/debug/libaimee_native.so --output .local/bridge-gpu.json
```

This gate isolates every module, includes upstream authentication/GGUF/hybrid
checks and fails if a test skips. To exercise the installed compiled kernels
and model library as well:

```sh
python3 distribution/vllm/tests/portable_gpu.py \
  --package aimee_gemma4_12b \
  --library /path/to/site-packages/aimee_gemma4_12b/native/libaimee_native.so \
  --output .local/portable-gemma4-12b.json
```

Repeat for each installed model namespace/library. These checks execute decoder
and attention kernels and the public Torch bridge, without model weights.
To compile device
operations for the declared architecture matrix without claiming execution:

```sh
PYTHONPATH=distribution/vllm python3 distribution/vllm/tests/portable_compile.py \
  --output .local/kernel-compile.json
```

The `_model.py` source binding is unbound:
it supports explicit ABI/command checks and refuses enrolled serving through the
development package. Production uses a dedicated installed model binding.

The standalone research Qwen/libtorch build has additional native Torch/ROCm
requirements; see [rust-runtime.md](rust-runtime.md). That server is separate
from the current vLLM product.

## Build five dedicated model wheels

Build in a clean Python 3.12 environment with Cython, setuptools, wheel and the
C++/Python development headers. The portable bridge has no linked GPU/ATen ABI;
its device operations execute through the inference host's qualified runtime.
No model weights are required to build wheels.

```sh
python3 -m pip install 'setuptools>=77,<81' wheel Cython build
python3 distribution/release/build-model-plugins.py \
  --output /absolute/path/to/new-build --version 0.3.4.dev0
```

The output directory must not exist. The builder defaults to this repository's
Rust inputs; `--rust-source /path/to/snapshot` is retained for explicit reproduction.
Only its manifest, lockfile, toolchain and native bridge inputs are copied, with
this repository's maintained adapter sources. Local caches, model files and
research outputs are not build inputs. The builder emits five model wheels and
one shared runtime, with AGPL metadata/LICENSE, independent namespaces, dedicated
Rust symbols and library hashes in each adapter binding. `0.3.4.dev0` is a local
validation version, not a published release claim.

The GGUF dependency and third-party notices are a separate finalization step.
Use the reviewed pinned GGUF wheel and the notice bundle collected for the exact
runtime/dependencies being shipped. For example:

```sh
python3 distribution/release/finalize-model-plugins.py \
  --wheels /absolute/path/to/new-build/wheels \
  --dependency /path/to/reviewed/vllm_gguf_plugin-0.0.5+triton-py3-none-any.whl \
  --notices /path/to/exact-notice-bundle \
  --output /absolute/path/to/final-wheels \
  --models gemma4-12b gemma4-26b qwen3-8-27b gemma4-e2b gemma4-e4b
python3 distribution/release/audit-model-plugins.py \
  --wheels /absolute/path/to/final-wheels --output /path/to/audit.json \
  --models gemma4-12b gemma4-26b qwen3-8-27b gemma4-e2b gemma4-e4b
```

Audit all five models explicitly; older three-model commands retain their default
scope for reproduction. The finalizer preserves executable bytes while updating
installer metadata and notices. It does not certify GPU execution or sign a release.
A binary audit also does not establish third-party redistribution rights.

Install the finalized wheel set into a fresh qualified environment, run `pip check`,
verify independent model bindings and perform enrolled/GPU lifecycle checks.
In an environment containing all five finalized model packages, the installed
CPU ABI/namespace/entry-point checks are reproducible without model weights:

```sh
python3 scripts/validation/installed-models.py \
  --expected-version 0.3.4.dev0 --output .local/installed-models.json
```

Ship the exact corresponding source, build instructions, license and notices;
record artifact hashes and signatures before publishing. Existing archived wheel
hashes cannot certify rebuilt source.

## Test an actual Aimee release

Use a fresh disposable host/environment. The harness below creates its own
randomly named Compose stack and always tears it down with volumes; it never
attaches to an existing application. It creates only synthetic personal memory
and a temporary owner/enrolled client. Review the target host's cleanup rules.

It consumes the release's own Compose/test helpers from an exact Aimee checkout.
For the current target use v1.0.2 / commit
`204d4e55828993a7683cb2610fb4165e44cabb9f`. Build the native launcher first:

```sh
cargo build --manifest-path distribution/launcher/Cargo.toml --locked --features model-plugin-client --bins
python3 scripts/validation/aimee-release.py \
  --aimee-source /path/to/clean/aimee-v1.0.2 \
  --launcher "$PWD/distribution/launcher/target/debug/aimee-native" \
  --application-image ghcr.io/rakuensoftware/aimee:1.0.2 \
  --postgres-image ghcr.io/rakuensoftware/aimee-postgres:1.0.2 \
  --embedder-image ghcr.io/rakuensoftware/aimee-embedder-a25m:latest \
  --output /absolute/path/to/new-evidence
```

Images must already be pulled. Prefer immutable digest references in retained
runs; the harness records the resolved image IDs. The embedder has an independent
image version; its `latest` reference above is resolved and recorded for the test,
not a recommendation to deploy a moving production dependency. Remove only images
and resources created by your test after retaining sanitized evidence.

When all five plugins are installed, add
`--installed-packages /absolute/path/to/environment/lib/python3.12/site-packages`
to also test every dedicated model binding's installed Rust connection client.

The harness checks real release readiness, normal enrollment, native-client
connection, populated unique source records, committed correction, restart and
revocation. It records verdicts and image identities without credentials. A
fixture-based TLS test and a real released server test are separate evidence.
The default release command does not run a model. To add installed model serving,
use `--serving-profiles /absolute/path/to/profiles.json`. The file is a JSON array
of ordinary model serving configurations (see [usage](usage.md)), each pointing
to a locally available checkpoint and model/tokenizer directory. Include its
exact checkpoint checksum/profile, adapter and supported runtime settings.
The matching dedicated wheel must be installed in the invoking Python environment;
put that environment's `bin` on `PATH`. Use one GPU with enough free VRAM and
host RAM for each profile and its explicit CPU offload, preserving existing jobs.
Triton also needs a working C compiler, Python development headers and discoverable
CUDA driver libraries at execution time. Confirm runtime warmup inside the actual
serving container/environment; host-only GPU detection does not qualify a guest.

The optional gate runs profiles sequentially against the harness's fresh enrolled
identity and real release server. It checks startup, authentication, the Qwen
hybrid prefix's system-context rejection, synthetic cold/warm recall and publication reuse, authoritative source
correction/new publication, and retirement. It creates only its own process groups
and short private `/tmp/ang-*` directories (Unix sockets have a path-length limit),
and terminates each model on completion or failure. The gate hashes each GGUF
before startup and rejects a mismatched declared checksum.
No existing service is stopped. Startup diagnostics remain private under `TMPDIR`;
public JSON reports contain verdicts and hashes, without credentials. Remove the
private scratch directory after inspecting failures. This gate does not claim
streaming, concurrency, multimodal, multi-GPU or arbitrary-checkpoint qualification.
