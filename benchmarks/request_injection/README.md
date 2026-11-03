# Request-bound memory after cached history

This is a research implementation for the frozen `Qwen/Qwen3-0.6B` attention
receiver, using its stock SDPA attention in FP32. It is not a deployment change
to the installed Gemma service and supplies no new production authorization.

The experiment compares persistent contextual text, text removed at scope end,
and a native bank attached at the injection point. Prefix-cached text is not a
fourth memory-scope arm. Every arm retains the unaffected history checkpoint;
text removal is not charged an unnecessary rebuild of earlier history.

## Mechanism

The receiver prefills each canonical record independently once. For an attachment
after H history tokens, its post-RoPE keys are re-rotated from positions 0..T-1
to H..H+T-1. Its values are unchanged. History tensors remain immutable. A
temporary execution cache joins history and selected state; task tokens contain
the question and assistant framing, without canonical record text.

The current turn's cache is memory dependent. Detachment therefore discards that
cache rather than retaining its tokens after deleting only the bank. Both scoped
arms append a clean public completion notice from the pre-injection checkpoint.
The persistent-text arm keeps the injected record and appends the same notice.
Private questions and generated answers are omitted from every public transcript.
This deliberately separates direct record retention from output-mediated influence.

Default full-attention RoPE is required. Re-rotation does not restore conditioning
of an independently encoded bank on its preceding history. No recurrent, hybrid,
local-window, or multiple-bank composition claim follows from this implementation.

## Frozen experiment

The main fixture has 24 distinct twelve-turn episodes: eight each at 128, 1,024
and 4,096 initial history tokens. Each episode has three unique random six-digit code versions, one
correction, unrelated probes and withdrawal probes. Each record is selected,
withdrawn and reselected. Three fresh model processes rotate arm order, giving
2,592 responses. The separate development fixture has four episodes and 144
responses. Main and development identifiers and values use distinct fixed seeds.

The identical system instructions explicitly expire prior request-only memory
in all arms. Thus persistent text is allowed to obey that instruction; stale
intrusion is measured, not assumed. Exact answer scoring and forbidden-value
intrusion are separate outcomes. Unrelated probes are simple instruction-following
controls, not a difficult distraction benchmark. Accumulation covers three versions
and six injections, not an unbounded session.

The final generation budget is 32 tokens. Color development panels cannot distinguish old-value echoes from chance guesses.
An eight-token development panel was
insufficient to observe complete abstention answers and is retained separately.
The earlier acknowledgment-imitation fixture is also retained, but does not carry
the main result. Loader/API failures produced no scored inference and remain in
their original NAS directories.

Report injection accuracy, exact withdrawal answers, stale intrusion, unrelated
accuracy, transcript length, prefill tokens, first-logit latency, generation and
cleanup cost. Preparation is separate; include it in a cold-cost accounting.
Timing uses CUDA synchronization and warmup, with no competing GPU workload.
The episode is the experimental unit. Greedy repeats quantify process variability,
not independent task evidence.

## Run

Artifacts must reside in the dedicated NAS directory on `.253`; the runner refuses
another destination. All weights, history caches, bank states and task caches are
CUDA resident, without offload. Sources, checkpoint files, token identities and
public-transcript identities are audited; hashes are forensic copies, not serving
offload. Run processes sequentially on the exclusive 5080:

```sh
python experiment.py /mnt/pve/backup/aimee-experiments/request-injection-20261011-r1/main-r1 \
  --model /path/to/pinned/Qwen3-0.6B --repeat 0
python experiment.py /mnt/pve/backup/aimee-experiments/request-injection-20261011-r1/main-r1 \
  --model /path/to/pinned/Qwen3-0.6B --repeat 1
python experiment.py /mnt/pve/backup/aimee-experiments/request-injection-20261011-r1/main-r1 \
  --model /path/to/pinned/Qwen3-0.6B --repeat 2
python score.py /mnt/pve/backup/aimee-experiments/request-injection-20261011-r1/main-r1
```
