# Installed vendor networking evidence

Collected from exact image `56e44a78b4ddbb228d5728311a709ee8118acc51f685b9f0e428a809b5ad2935` without installing or changing packages.

- `ionic-common` has 17 regular non-symlink files, no ELF or static archives. Sixteen text files were retained, including the Bash `show_gid` program and package copyright; the remaining compressed changelog was not copied. Its installed program is already supplied as source, so an uncollected source-package archive must not be described as a missing compiled driver implementation.
- `libionic` has a shared library/static archive plus retained headers and copyright. Its copyright distinguishes file groups and alternative licenses; a package-wide GPL keyword is not a sufficient classification.
- `bnxt-rocelib` headers contain full copyright and a GPL/BSD choice. One header also has a GPL-only SPDX line; both statements are preserved. These header notices alone do not settle every library file's licensing.
- `hsa-amd-aqlprofile` lists a single ELF library and symlinks; this inspection did not find package-owned text notices. Upstream notice mapping remains required.

This is content evidence, not a blanket legal approval or a claim that corresponding-source fulfillment is complete. No private Aimee implementation, credentials or model weights were collected.
