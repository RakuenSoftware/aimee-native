# Historical CPU preparation reference

These are the retired private Python model compilers, copied before retirement
of their current `distribution/service` entry points. They preserve research
comparison code for the prior CPU BF16/FP32 and negative-position studies.
They are excluded from model plugin builds and are not current adapters.
New native preparation uses each model's dedicated Rust adapter and its vLLM
plugin. Reproduce historical results against their archived runtime and source
snapshots; their tensor profiles do not establish new-plugin compatibility.
