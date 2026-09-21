# Third-party code and runtime dependencies

`src/model.rs` ports the Qwen3.5 text forward-pass equations from Transformers
5.17's `models/qwen3_5/modeling_qwen3_5.py` into Rust/libtorch. The changes replace
Python orchestration with Rust and add the existing Aimee attention callback,
RAM-resident memory banks, and frozen per-row INT8 loading.

Original notice: Copyright 2025 The Qwen Team and The HuggingFace Inc. team.
All rights reserved. Licensed under the Apache License, Version 2.0.
The license is included in `licenses/Apache-2.0.txt`.

The adapter uses native libtorch through tch/torch-sys, Rust tokenizers, and
other dependencies pinned in Cargo.lock. Their licenses and notices remain
applicable to redistribution. A private adapter binary does not remove those
obligations. Qwen model weights are separately supplied and are not included.
