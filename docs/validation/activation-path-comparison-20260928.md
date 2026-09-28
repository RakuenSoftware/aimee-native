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
CT101 process 368787 was confirmed live after launch. Results are pending;
no implementation change or speedup is claimed yet. The direct arena mount
was confirmed as ext4 on `/dev/mapper/storage-vm--101--disk--0`, not tmpfs.
