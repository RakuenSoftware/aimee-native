# Gemma 4 native-memory demonstration

Scope: reuse Aimee's published memory and existing native K/V interface with
Google Gemma 4 12B Instruct. No composition or capacity benchmark.
Checkpoint: google/gemma-4-12B-it, revision
707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7.

The model remains loaded and frozen. Read one synthetic general fact, change
its value through real image build/approval/publication, then read it again
using identical conversation token IDs. Include a disabled-memory control.
The memory text is encoded separately; only native states reach attention.
Gemma's memory positions precede the conversation. No training or prompt facts.

Record exact outputs, expected values, prompt IDs, native reads, canonical
record revisions, parameter-version checks and publication versus answer time.
The source is a research fixture and does not exercise production policy.
The same model-independent canonical record format and Go publication tools
are used by the Qwen demonstration.

Final result and integration corrections: `docs/validation/gemma-native.md`.
The original question and record values remained unchanged across attempts.
