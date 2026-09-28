# Activation path diagnosis

The requested cold/warm microsecond application target remains unmet. This
bounded diagnostic tests two implementation choices before modifying the
validated runtime: container overlay versus a direct Optane-backed directory,
and overlapping chunk uploads versus one upload after parallel reads finish.

Both storage arms use Optane. The original temporary arena resides in the
container overlay backed by CT101's Optane root filesystem. The shared fixture
source resides on the host's SATA pool, but the timed lossless-transport reads
use the prepared arena, not that fixture file. Earlier attribution of the
measured cold latency to the SATA pool was incorrect.

The unchanged image is
`56e44a78b4ddbb228d5728311a709ee8118acc51f685b9f0e428a809b5ad2935`.
The fixed Gemma bank has 36,632,124 source bytes and 60 rank-zero tensor
segments. Each arm checks byte fidelity and measures 10 independently cold
applications, 100 warm applications, and 100 resident lookups. Four arms run
in forward and reverse order. This isolates application overhead; it does
not measure answer generation or establish performance across every bank.

Coordinator: `distribution/tests/activation_path_comparison.py`.
Remote output: `/opt/aimee-large-release-validation/activation-path-comparison-r1`.
The coordinator completed all eight runs. The direct arena mount was confirmed
as ext4 on `/dev/mapper/storage-vm--101--disk--0`, not tmpfs.

## Completed measurements

Ranges below are the two per-run medians, not pooled sample estimates.

| Path | Cold application (ms) | Warm application (ms) |
|---|---:|---:|
| Overlay, overlapping upload (current) | 14.84–14.87 | 5.01–5.24 |
| Direct, overlapping upload | 14.85–15.11 | 5.00–5.27 |
| Overlay, bulk upload | 17.61–17.93 | 5.89–6.53 |
| Direct, bulk upload | 17.59–17.63 | 6.24–6.60 |

All eight runs passed exact reconstruction of 60 tensor segments. Sample counts
were verified: 80 independent cold applications, 800 warm applications and
800 resident lookups overall. Raw files and coordinator-recorded result hashes
are preserved in [the evidence archive](artifacts/activation-path-comparison-20260928/).

The container overlay does not explain the cold-read bottleneck in this bank.
Removing overlap worsens both measured cold and warm application. Keep the
existing pipeline; neither alternative is a supported performance fix.

The current transport carries a losslessly encoded BF16 bank, not a few
kilobytes of token IDs that can simply be reinterpreted as the same tensors.
For this bank, even the stored transport payload is 36.6 MB per rank. A
microsecond-scale cold application therefore needs substantially less data
movement, rather than just different file placement or upload scheduling.
A replacement representation must be evaluated against native task quality;
lossy reconstruction cannot be passed off as the byte-identical representation
validated here. Already-resident lookup timings do not establish cold-load
performance. The existing candidate remains unchanged, and the requested
cold/warm performance target remains unmet.
