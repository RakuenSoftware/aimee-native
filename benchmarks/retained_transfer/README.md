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

The receiver seven-arm driver and the ten-turn variant still require completion
and mechanical validation. No C1–C5 result is claimed by this readiness code.
Related-work checks are tracked in [RELATED_WORK_AUDIT.md](RELATED_WORK_AUDIT.md).
