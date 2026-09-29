# Installed-wheel coding evidence

See the [validation report](../../standalone-coding-20260929.md) and
[frozen protocol](../../../protocols/standalone-coding-20260929.md).

- `status.json`: evaluator outcomes, timings, patches, and trajectory hashes.
- `summary.json`: derived condition totals, paired outcomes, initial prompt
  counts, modified files, and official test-status counts.
- `manifest.json`: frozen input, runner, and publication identities.
- `campaign.tar.gz`: evaluator source, frozen agent-visible inputs, complete
  trajectories, result files, and separate official grading outputs.
- `host-*`: environment identity, actual executed coordinator, explicit setup
  correction, and compressed installation/server/operator logs.
- `checkpoint-12.json`: the original halfway snapshot, retained unchanged.
- `SHA256SUMS`: hashes of the evidence files alongside this document.

Run `sha256sum -c SHA256SUMS` in this directory to check the bundle. Extract the
campaign archive into an empty directory to inspect individual attempts or
rerun its included `summarize.py` against the archived status and trajectories.
The evidence contains no model weights, authority credentials, or private
grader-only input file.

`native-repeat` uses the same frozen memory in a fresh attempt. It is not a
learning round. `TimeExceeded` is the agent's stopping condition, not the patch
grade: a patch already written can still pass. `empty_prediction` means that
no patch was available for grading. Official test counts are subordinate to
the issue outcome; a collection error can mark expected tests unsuccessful
without executing their individual assertions.

The legacy `native-20260926-` grading-directory prefix comes from the frozen
runner; this campaign's manifest and timestamps identify the 29 September run.
The runner also retains an unused legacy learning helper. This campaign calls
only its attempt path and never invokes that helper or updates a memory.
