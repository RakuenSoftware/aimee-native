# One native-memory plugin per supported model

The release contains three separately installable vLLM plugins. Each plugin has
one dedicated Rust adapter, its own package namespace and its own native library.

| Model | Package / plugin entry point | Rust implementation |
|---|---|---|
| Gemma4 12B | `aimee-gemma4-12b` / `aimee_gemma4_12b` | `src/model_adapters/gemma4_12b.rs` |
| Gemma4 26B A4B | `aimee-gemma4-26b` / `aimee_gemma4_26b` | `src/model_adapters/gemma4_26b.rs` |
| Qwen 3.8 27B | `aimee-qwen3-8-27b` / `aimee_qwen3_8_27b` | `src/model_adapters/qwen3_8_27b.rs` |

There is no generic adapter with model switches. Shared infrastructure supplies
byte publication, storage, transport and ABI ownership. Each adapter defines
its own accepted architecture, memory geometry and position mapping. Qwen's
adapter also defines recurrent-prefix layout and initialization decisions.
The private development build can exercise all three entry points; each release
build selects exactly one Cargo feature and checks the exported symbol table.
Selecting multiple release adapters is a compile error.

Enrollment, authenticated source selection, immutable caching, authority
rechecks and process supervision belong to one shared Rust runtime package,
`aimee-native-runtime`. All three model plugins depend on the same version of
that package. It contains one connection binary and one copy of the common
vLLM bridge: preparation, admission, scheduling, lifecycle control, cache/store
readers, tensor operations and telemetry. These are not separately compiled or
copied into each model wheel; model wheels supply small bindings and their
dedicated Rust library.
Each plugin supplies its own adapter binding and library checksum to that
runtime. The shared runtime has no model architecture registry, cache geometry
or rotary-position implementation. Model-specific capture requirements are
described by each dedicated Rust adapter and consumed by the shared bridge.

Gemma memory is captured from the stock quantized model at ordinary positions
`0..M`. Its dedicated adapter positions the live conversation after that prefix.
The integration neither supplies negative positions to Gemma nor changes the
model's rotary cache. The failed experimental negative-position capture is
superseded; its existing logs remain evidence of the failure.

The Python layer registers vLLM's backend and worker, observes framework tensors,
and passes runtime requests through the ABI. It does not implement model
position mapping. GPU attention and runtime tensor operations still execute
through the installed vLLM/Torch/Triton interfaces. Compiling framework glue with
Cython does not make that glue Rust; source inventories must retain that distinction.
The release excludes the older generic Python preparation compiler.

Model weights, tokenizer/config identity, precision and publication identity
remain bound to the serving instance. An adapter for another model, an altered
layer layout, incomplete memory or a legacy Gemma publication fails admission.
Re-encoding is required for the new Gemma position protocol. Aimee remains the
authoritative source of authorized memory and writes.

Build the three packages with `distribution/release/build-model-plugins.py` using
a pinned complete private Rust build snapshot. Install the package corresponding
to the model, then run its model-specific console command with the serving config.
The plugin binds its adapter and defaults to its bundled library. Explicitly
selecting a different model is rejected. Installations may coexist because their
module namespaces and console/plugin names are distinct; the command selects
only its own vLLM plugin.

Validation must distinguish Rust/ABI and wheel-isolation checks from actual
model execution. A passing config check alone does not certify a checkpoint,
quantization, device or end-to-end recall result.

Implementation and candidate validation are recorded in the
[model-plugin release report](../../validation/native-memory-serving-and-model-plugins-20261004.md).
