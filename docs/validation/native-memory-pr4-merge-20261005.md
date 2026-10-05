# PR 4 base-branch integration

Merged `69bb4d8` (PR 3) into the shared-runtime release branch. The five conflicts
concerned enrolled TLS pinning, the retired wheel builder, the retired CPU compiler
entry points and the portable bridge's Python import.

The enrolled client retains its exact-leaf verifier and TLS signature checks.
The portable bridge imports `aimee_native_runtime.runtime_ops`. Both files are
byte-identical to the validated 0.3.2 release source. The older wheel builder
retains upstream packaging fixes but refuses execution and directs callers to
`build-model-plugins.py`. The CPU compiler entry points remain retired.

Upstream CPU solver fallback, request position binding and GGUF restoration fixes
are retained in `benchmarks/native_addressing/legacy_cpu_preparation`. The two
compiler regression modules now import that historical implementation. Negative
positions in those tests describe the historical compiler, not current Gemma
adapter behavior. No historical evidence archive or candidate wheel was changed.

Validation after resolution:

- Four model-plugin packaging tests and 43 offline addressing/audit tests pass.
- Five merged historical compiler and GGUF regressions pass in an isolated test
  directory on `.253`, using the clean release Python environment. Their tiny
  reference models run on CPU. Accelerate 1.15.0 was installed into that test
  directory only; the serving environment was not modified.
- The retired wheel builder fails before creating output; retired compiler entry
  points refuse execution. Modified Python parses and the merge diff passes
  whitespace checks.
- All retained evidence and candidate bytes match the pre-merge branch.

This resolves source integration conflicts. The earlier RTX 5080 deployment and
model validation results remain tied to their recorded artifacts; no new GPU
validation is claimed for this merge.
