# Shared runtime and dedicated model plugins

This supplements the [earlier model-plugin report](native-memory-serving-and-model-plugins-20261004.md).
Its 0.3.0 artifacts, results and evidence remain unchanged. The shared 0.3.2
release candidate passes the recorded execution, enrolled lifecycle, installation,
deployment and rollback gates on the owned RTX 5080 environment.

## Package boundary

Three independently installable model plugins depend on exactly one
`aimee-native-runtime==0.3.2` package. That package contains one Rust connection,
selection and supervision binary and one compiled copy of the vLLM bridge.
Admission, preparation, worker scheduling, lifecycle control, storage/cache
readers, tensor operations and telemetry share the same module objects.

Each model package carries its dedicated Rust library, its binding contract,
registration, command forwarding and compatibility imports. Each library
exports its own adapter; geometry, positions and recurrent initialization are
bound to that adapter. A process selects one plugin. Co-installation preserves
the independence of the three adapter contracts.

The common bridge is pinned to vLLM 0.30.0. The current wheels target Linux
x86-64, CPython 3.12 and glibc 2.39 or newer; the candidate ELF inventory records
all 27 executable members and their shared-library dependencies. Execution
coverage is single-GPU, text-only V1 serving on CUDA device 0 with eager/synchronous
execution and prefix caching disabled. The checkpoint profiles are Gemma 12B
Q4_K_M, Gemma 26B A4B Q3_K_M, and Qwen 27B FP8 with the recorded CPU offload.
Python remains for framework
integration; compiling it with Cython does not make it Rust. The model command
delegates to the shared runtime and supplies its own checked adapter binding.
Gemma uses stock positive-position capture and its Rust position mapping.

The 0.3.2 candidate retains shared command forwarding and adds two repairs
found in the enrolled lifecycle gate. The common admission bridge delegates to
vLLM's stock authentication middleware before body reads or source selection.
The dedicated Qwen Rust adapter renders and validates its closed system prefix;
the stock Qwen chat template requires a user query and cannot render that
prefix alone. Gemma continues to use its stock tokenizer template. The shared
preparation code selects the renderer declared by its adapter.

## Completed execution gates

The independent clean dependency environment has vLLM 0.30.0, Torch metadata
2.13.0, CUDA 13.0 and Triton 3.7.1. Its Torch metadata differs from the older
borrowed runtime's `2.13.0+cu130`, so Qwen's complete FP8 prefixes were freshly
encoded through the stock consumer engine. No stored arithmetic identity was
edited to reuse an older prefix.

Both the earlier shared-runtime matrix and the installed 0.3.2 Qwen matrix
pass **324/324**: 48 frozen tasks and six held-out
phrasings, native and matched text, with 0/16/48 previous turns. Actual Gemma
shared-runtime tests previously passed 25 lifecycle checks each for 12B Q4_K_M
and 26B Q3_K_M, including preparation through the resident model. The final
0.3.2 native-library artifacts pass 21 enrolled lifecycle checks per installed
plugin through the normal enrolled path.

The current source passes 31 portable native Rust tests, 23 shared Rust client
tests, **87 serving bridge tests without skips** (including actual CUDA reference
comparisons on the RTX 5080), four packaging regression tests and 43 offline
regression tests. An initial bridge run lacked its offline exporter helper in
the validation checkout; after restoring that test dependency, the two affected
tests and then the complete 87-test suite pass. The
client process tests run in parallel; the released-lock assertion allows an
inherited descriptor to close during a concurrently forked child's exec.
This changes the test, not the runtime lock implementation.

A separate packaging environment installs all three plugins on one common
runtime. Uninstalling Gemma 26B preserves 84 files belonging to the other plugins
and runtime byte-for-byte; reinstalling it restores its independent binding.
This check uses read-only dependency links from the independently installed
clean environment and supplements that environment's dependency-resolution proof.

## Actual enrollment and source authority

An isolated core server and PostgreSQL database on the owned host provide the
real issuer, store and source API. A trusted root Unix-socket owner request
creates the invitations, and the normal Aimee client completes CSR enrollment.
This is the local owner-proxy contract, not a browser/PAM login test. No knowledge
server, replacement issuer or hand-written client grant is used.

The installed plugin reads the standard enrolled profile. It stores its path,
checks its private credential permissions, uses its bearer and client certificate,
and rechecks source authority on warm reuse. The enrolled leaf is pinned exactly,
matching the standard client's behavior; TLS handshake signatures remain verified.
A raw TCP-mapped loopback endpoint absent from the leaf SAN succeeds with that
pin and fails with a different pin.

Real source export exposed overlapping identity and recent-context sections.
Core now emits unique immutable source versions, caps the exported working set
at 32 records, and rejects conflicting overlapping rows. The integration keeps
its duplicate-row rejection. The isolated core dependency is baseline
`4e822e6ee` plus the export repair in `src/server/server_api.c` and its API description.
The export repair belongs to core, rather than another policy implementation in
the plugin. Its live store, CA and existing enrollments survive the server repair.

The initial export attempts retain corrected test assumptions: 36 ordinary
synthetic writes produced a bounded three-row view, not a requirement to return
32 rows; a missing enrolled certificate returns 401; a revoked certificate is
rejected during TLS, before an HTTP status can be returned. Follow-up checks
confirm that revocation rejects that device and preserves another enrolled
device's access. Every additional canary was retired through the ordinary owner
API. These results cover personal-memory authority in this owned environment.

The first installed Gemma 12B enrollment gate recalls `68731`, reuses its warm
bank, accepts an ordinary owner update to `94562`, and derives a new bank through
the resident engine. The measured calls take 0.900 s cold, 0.787 s warm and 4.471 s
after the update. These include selection and model consumption and are single
observations, not isolated routing or kernel benchmarks.

The installed 0.3.2 plugins each pass **21/21 actual enrolled lifecycle checks**:
withdrawn startup, authentication before source selection, cold and warm recall,
source update and new bank, ordinary retirement with empty view, reactivation,
complete-profile mismatch rejection and restoration. This uses the Qwen adapter
prefix renderer and Gemma stock templates through the resident model. The
current Qwen matrix also passes 324/324 and its independent auditor passes.
Operational checks observe one actual preemption and 144 reseeding events, return
401 for missing authentication and 400 for a changed system context, maintain
withdrawal after an invalid-precision refresh (503), and restore the correct
`7391` canary. Peak native device residency is 480,313,344 bytes, below the
536,870,912-byte budget. These are separate from the model weights and KV cache.
No authorization for shared organization memory is inferred from public fixtures
or these personal-store checks.

## Deployment and delivery

The owned `aimee-native-serving.service` on `192.168.1.253` runs the shared
0.3.2 release in the independently installed clean environment. The deployed
release is `/opt/aimee-native-serving/releases/shared-model-plugins-20261004-r12-r2`.
It passes its live canary, an actual rollback to the previous unit/configuration/
release, and restoration of the shared release with another correct canary.
The final service is active and enabled, restarts on failure, retains its
three-starts-per-hour limit, and uses a mode-0600 control socket. The deliberate
rollback transitions clear the failure counter between starts; the production
unit's limit remains unchanged. A separate request from the repository workspace
gets 401 without credentials and the correct `7391` answer with credentials.

The first R12 enrolled runner omitted its API-key environment file and is retained
as a setup failure. Its retry passes all three model checks. A competing restoration
attempt also hit the prior service's start limit; the final serialized deployment
and rollback gate completes successfully. Product failures found in R11 (source
work before authentication and the Qwen system-only template error) were repaired
in the 0.3.2 artifacts rather than relaxed in the tests.

The [candidate directory](../../distribution/release/candidates/shared-model-plugins-0.3.2-20261004)
contains the four Aimee wheels, the pinned GGUF dependency, hashes, ELF dependency
inventory and installation instructions. Dependency notices are included; the
inventory is not a separate legal-approval claim. The normal source API depends
on the recorded core export repair, included as a patch with its baseline and hash
in the evidence. Core integration remains separate from the plugin's model code.

The [immutable evidence archive](../../benchmarks/native_addressing/evidence/20261004-shared-model-runtime/raw.tar.gz)
has SHA-256 `dbc5439e151055b5a7494a0f1e3086087e684e4a25673173ab32754b25bf58f3`,
5,424,164 bytes and 281 files. It retains earlier failed attempts and later
passing gates, source/compiler inventories, the core prerequisite patch, notices,
wheel bytes and synthetic result logs. Credentials, enrolled profiles, private
keys, model weights and tensor payload packs are excluded. The separate
[independent audit](../../benchmarks/native_addressing/evidence/20261004-shared-model-runtime/independent-audit.json)
verifies every member digest and that the delivered candidate wheels match the
deployment evidence; [the network check](../../benchmarks/native_addressing/evidence/20261004-shared-model-runtime/network-check.json)
records the final workspace-to-host probe. Earlier 0.3.0 evidence remains unchanged.
