# Linked retained-learning study

The frozen design is in [PROTOCOL.md](PROTOCOL.md). Generated data and all run
outputs live on the GPU host's dedicated NAS directory:
`/mnt/pve/backup/aimee-experiments/retained-transfer-20261011-r1`.

The original v1 calibration sessions each scored 0/480. Their acquisition run
is excluded: an agent-added bare-JSON record gate rejected written rules before
application validation. All original requests and outputs remain archived; no
learning conclusion is drawn from that run.

The corrected cycle uses fresh seed `retained-transfer-20261011-v2-written-rule`,
frozen protocol and source commit `9afd2fe`. Its data and receipts are in
`corrected-cycle-r2/` below the NAS root. It reruns all four calibration sessions
before acquisition, preserves the learner's exact written record, and accepts
prose or fenced/nested JSON. Validation parses only the eight-answer transport.
Scored cases from v1 are not retried or reused. The same private canonical store
is reused explicitly; only readiness probes, no acquired v1 rules, preexist.

The acquisition controller first checks a separate, disposable Aimee store's
actual memory-store/get operations. Accepted proposals are admitted and read
back unchanged while producer session A is still alive. Only then may the
producer terminate and fresh scored receiver sessions begin. Global retrieval
readiness is preserved separately; retrieval is outside this exact-record study.

Scripts:

- `generate.py`: three language fragments, disjoint training/calibration/held-out vocabularies.
- `calibrate.py`, `calibrate_installed.py`: None controls, no learning inputs.
- `acquire.py`: training-only model proposals and separate application checks.
- `acquire_installed.py`: source/hash and session gates, canonical admission before termination.
- `canonical_store.py`: real owner API write/read-back, no stand-in database.
- `make_store_boot.py`: private mount/network namespace, disposable NAS-backed store.
- `mechanical_receiver.py`: non-study native/text cache-continuation gate.
- `analyze.py`: complete-coverage checks, family-unit bootstrap, paired tests and Holm correction.

## Execution status (12 October 2026)

The corrected acquisition completed with seven admitted records from 60 families.
Every accepted raw proposal was validated on training examples and read back
unchanged from the isolated Aimee owner API before the producer ended.

All three HF receiver profiles passed their non-study native-continuation checks.
Their seven-arm evaluation completed: 75,600 requests across three receivers,
three fresh processes per receiver, and 1,200 held-out inputs per arm. Repeated
requests do not increase the statistical unit beyond the 60 rule families.
The fresh installed 12B learner-retention evaluation is running (25,200 planned
requests). Its separate mechanical and token-budget checks passed; the primary
four-receiver analysis awaits its completion.

A secondary context-growth phase is frozen and queued after retention:
`context_growth.py`, three HF receivers, three fresh processes each, twenty
seven-turn episodes per arm, 3,780 requests total. Seven admissions support seven
turns, rather than the originally proposed ten distinct-record turns. Its arms
are persistent text, removed text and request-bound native records. Persistent
text serializes prior rule blocks into reconstructed history; all arms retain
public tasks and generated answers. Prompt/history caching is disabled. This
phase uses the complete-prefix reference profile, not mid-turn insertion after
cached history. It measures full preparation wall time separately from model
prefill, prepared-state residency, carried tokens and per-turn latency. Its
cache byte-seconds quantity is explicitly a proxy, not an allocation-time
integral; energy is not measured. The installed 12B context phase remains to be
implemented.

All outputs, source freezes and process receipts remain in the dedicated NAS
campaign directory. Scored failures are retained; results are not retried to
change their outcomes. Final claims and family-clustered inference require the
complete analysis and acquired-record diagnostics.
Related-work checks are tracked in [RELATED_WORK_AUDIT.md](RELATED_WORK_AUDIT.md).
