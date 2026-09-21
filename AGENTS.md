# Qwen memory integration ownership

Use this repository for all Qwen/Aimee memory integration code, experiments,
tests, design notes, validation reports, and associated evidence. Do not add
those files back to the sibling `aimee` repository.

The sibling `../aimee` owns model-independent memory storage, governance,
authorization policy, image compilation, and the `aimee-memory-image` CLI.
Consume those components as dependencies; do not copy their implementation here.

The current adapter is read-only and untrained. Memory learning, authorization,
selection, and updates belong to Aimee. Historical trained-projection experiments
remain under `benchmarks/` as research evidence, not the current adapter design.

Start with README.md and the latest authorization-transition report. Preserve
archived result bytes and historical runtime paths/hashes; document corrections
in reports rather than rewriting experiment evidence. Never commit authority
credentials, private signing keys, model weights, or private production memory.

Use the documented test commands. Research fixture grants do not establish
production authorization integration. Keep that distinction in results.
