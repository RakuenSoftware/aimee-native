# Linked retained-learning study

The frozen design is in [PROTOCOL.md](PROTOCOL.md). Generated data and all run
outputs live on the GPU host's dedicated NAS directory:
`/mnt/pve/backup/aimee-experiments/retained-transfer-20261011-r1`.

The four calibration sessions have completed: each receiver scored 0/480 with
lexicon only on separate calibration phrases. These are prerequisite controls,
not learning or transfer results. The training and held-out exports are frozen
at commit `1bbf683`, with full file hashes in `fixture/freeze.json` on NAS.
Runtime corrections have separate source snapshots and additive receipts.

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
- `analyze.py`: complete-coverage checks, family-unit bootstrap, paired tests and Holm correction.

The receiver seven-arm driver and the ten-turn variant still require completion
and mechanical validation. No C1–C5 result is claimed by this readiness code.
Related-work checks are tracked in [RELATED_WORK_AUDIT.md](RELATED_WORK_AUDIT.md).
