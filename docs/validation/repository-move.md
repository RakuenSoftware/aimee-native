# Qwen memory repository move

Date: 2026-09-20. Destination: `/home/virant/dev/aimee-qwen`, existing remote
`git@github.com:RakuenSoftware/aimee-qwen.git`.

Moved 753 files (39,666,794 bytes excluding Python bytecode) from 35 source
paths in the sibling `aimee` checkout. These include the Qwen integration,
native-memory and latent-projection experiments, local-memory benchmark drivers,
20 validation reports, the local sparse-memory proposal, and ten artifact trees.
The original source paths no longer contain these files.

[The manifest](../repository-move-2026-09-20.json) records SHA-256 for every moved
file immediately after relocation. Only six moved source/documentation files
subsequently changed to fix cross-repository paths, fixture lookup, build
instructions, and the adapter README's obsolete startup example. Archived
results and evidence retain their exact bytes and historical source identities.

General Aimee memory/image implementation, its CLI, canonical authorization
policy, and general poison fixtures remain in Aimee. Its sparse-reader README
now links here instead of maintaining Qwen-specific serving instructions.

New root README, AGENTS.md, .gitignore, and go.mod establish this repository's
ownership and build path. The research fixture issuer imports Aimee's image
types through a local Go module replacement; no core implementation was copied.
The historical poison-fixture test reads the sibling Aimee checkout and supports
`AIMEE_SOURCE` for an alternate checkout.

## Validation

| Check | Result |
|---|---|
| Every moved file hash immediately after relocation | 753/753 match |
| Archived result/evidence bytes after path updates | Unchanged |
| Relative Markdown links, including cross-repository dependencies | No broken links in maintained docs |
| Reader build from Aimee and fixture issuer build from aimee-qwen | Passed |
| Go package compilation (`go test ./...`) in aimee-qwen | Passed; fixture command has no Go tests |
| Local authorization-only suite from new repo | 10 passed |
| Full current adapter suite from relocated layout on `.253` | 42 passed in 0.968 s |
| Historical P0 suite with sibling Aimee fixture dependency | 11 passed in 0.374 s |
| Python compilation of integration and native/local benchmark drivers | Passed |

Test durations are not serving performance measurements. The remote validation
snapshot is under `/opt/aimee-qwen-repository-validation-20260920`, containing
the new repo layout and only the two required Aimee poison-fixture source files.
It uses the existing research Python environment and tiny Qwen models; no
production service, model weights, authorization, or memory database was changed.

[Adapter and historical test output](artifacts/repository-move-2026-09-20/).
No commit or push was made; files are in the requested repository working tree.
