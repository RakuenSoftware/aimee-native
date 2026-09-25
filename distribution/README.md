# Aimee Native distribution

Private implementation work. All runtime integration, preparation, packaging,
release design, tests and evidence stay in `RakuenSoftware/aimee-qwen`.
Aimee remains authoritative for memory, selection, permissions and publication.
Nothing in this directory has been released publicly or deployed as a service.

## Intended user experience

Install one platform package, connect Aimee, select a supported model, run it.
No user compilation, Python installation or tensor settings. The implemented
Linux launcher commands are:

```
aimee-native connect https://your-aimee-endpoint   # scoped token on stdin
aimee-native install <certified-model-id>
aimee-native run
```

The launcher implements configuration, signed artifact download, installation,
rollback and process launch. No certified model catalogue or release origin is
provisioned yet. `install` refuses to proceed without a compile-time release
origin and public verification key. `run` requires a certified runtime with the
Aimee flags; upstream llama-server does not implement them. Browser sign-in,
hardware-specific package selection and automatic updates are pending. Current
`connect` stores credentials locally; it does not claim to authenticate against
an undeclared Aimee API. `doctor` never reads or prints their contents.

## Distribution boundary

- Hosted preparation: proprietary preparation/encoding and model-specific
  compilation, behind the existing authoritative Aimee publication boundary.
- Client: compiled Rust application engine, local owned memory store and RAM
  index, supported inference runtime, model, public notices.
- GGUF: model artifact and compatibility metadata. Not executable integration.
- Public integration surface: versioned opaque handles and runtime callbacks.
- Source, preparation tools, fixtures, research diagnostics and private symbols
  never enter the client package. The release tool copies explicit files only.

Preparation and synchronization run outside attention execution. A local memory
hit does not depend on a per-token network call. Complex/missing memory can reach
Aimee. Existing authoritative selection and publisher-controlled install,
replacement and withdrawal must be reused, not reimplemented as client policy.

Shipping an entire preparation service to a customer reduces the secrecy benefit.
A host owner can inspect local code and usable memory/tensors. Binary protections
increase effort; they do not prevent reconstruction or copying of delivered data.

## Implemented and verified

1. Standalone Rust launcher, Ed25519-signed manifests, HTTPS streaming downloads,
   exact sizes/hashes at installation, package allowlist, staged installs, atomic
   active-release switch, interprocess update lock, explicit rollback and release
   sequence downgrade protection. No new hash checks in the attention path.
2. Client-only feature excludes preparation FFI and compiler entry points; generic
   client error messages; research diagnostics retained only in research builds.
   Export allowlist, source-path remapping and stripped release artifact audit.
3. Pinned llama.cpp patch exposing an in-process graph callback, plus private
   provider loader with an independent versioned ggml interface. The library
   builds; loader interface tests pass. These are integration foundations, not
   end-to-end native Gemma results.
4. Private preparation-worker cache primitive: full ordered record/revision set,
   authorized view, recipient, model, runtime/quantization profile, encoding and
   positional policy participate in identity. Atomic output publication and
   per-key interprocess compilation coalescing; failures do not become hits.
5. Torch-free prepared-store reader sharing the compiler’s format declarations.
   Admission verifies the publication once; pinned immutable views need no file
   access or hashing. This removes the storage reader’s Torch dependency, not yet
   the device/graph bridge’s dependency.
6. Private package assembler and mandatory release-gate declarations. Signing
   keys stay outside source/client artifacts; evaluation reports stay private.

## Runtime gap and release gates

The tested Rust client currently imports/exports DLPack through LibTorch. It is
NOT a ggml-native provider and does not export `aimee_native_ggml_get_api`.
`llama.cpp/provider.cpp` explicitly rejects incompatible libraries. The launcher
contract's Aimee CLI flags and provider lifetime must still be wired into
llama-server. No inert fallback to plain inference is acceptable.

The first hook supports a single sequence and ordinary attention, with graph
reuse disabled while a provider is active. Multi-sequence mapping, revision
lifetimes, sliding-window/position parity and graph reuse need backend-specific
implementation and tests. This release restriction does not alter the paper's
architectural generality argument or claim new DeepSeek measurements.

Required before a first external preview:

- ggml tensor/device ownership and lifetime bridge; no forced LibTorch dependency.
- Aimee-authorized preparation input, hosted worker and publication feed wiring.
- Reusable preparation in the actual serving pipeline. The new cache primitive
  coalesces exact selections but does not prove arbitrary record-bank composition
  or remove the cost of unseen working sets. Benchmark this explicitly.
- GGUF quantization parity for the first Gemma release and every selected record
  reaching the native encoding/attention path.
- Long conversations, local/global attention semantics and persistent context
  savings; recipient/session separation and revision/withdrawal behavior.
- Cold/warm total latency and memory budgets on the shipped backend; performance
  measured separately from server preparation. No microsecond claim from builds.
- Clean-machine installation and recovery; GPU-driver/runtime compatibility.
- Final package, dependency notices and binary disclosure audit.

`package.py` requires private passing evidence for every release gate before
signing. These reports are release decisions, not substitutes for empirical tests.
No passing production gate reports have been manufactured for the prototype.

## Build and validation

```
cargo test --manifest-path distribution/launcher/Cargo.toml
cargo test --no-default-features --lib preparation_cache
python3 -m unittest discover -s distribution/tests -v
sh distribution/tests/test-provider.sh /path/to/patched/llama.cpp
```

The library's client build needs the existing LibTorch toolchain until its bridge
is replaced. `distribution/release/build-client.sh` builds only the client library
and audits the final artifact. `build-launcher.sh` requires a public release key
and HTTPS release origin; never pass signing keys to a client build.

The initial runtime revision is in `llama.cpp/runtime.lock.json`. Apply the patch
only with `llama.cpp/apply.sh`; it refuses other upstream revisions. Keep provider
code private. The patch exposes a generic runtime integration point, not memory
encoding algorithms or record construction.

## Next implementation order

1. Finish ggml provider and llama-server configuration/lifetime integration.
2. Wire the preparation cache around the real compiler, then authorized feed and
   background local publication. Confirm hosting endpoint with the owner.
3. Run Gemma release gates against the actual quantized distribution.
4. Provision release signing/origin, build the installer, conduct a limited binary
   preview, then add vLLM using the same ownership and preparation boundary.
