# Latent projection research probes

Research probes only; no Aimee database access or production recall integration.

- Phase 0: model metadata, tokenizer output, PLE addresses, and isolated overlay
  byte mechanics. The commands below reproduce that phase.
- [Phase 1](phase1/README.md): a synthetic single-fact compiler and isolated
  native inference experiment. Reversible training-prompt injection passed;
  useful recall across prompts was not established. See the
  [Phase 1 report](../../../docs/validation/latent-memory-projection-phase1.md).
  The [Phase 1 continuation](../../../docs/validation/latent-memory-projection-phase1-multicontext.md)
  records 170 further final-comparison trials of multi-context training and
  zero-added-token footer activation; neither compiler attempt matches text recall.

Read the [capability report](../../../docs/validation/latent-memory-projection-phase0.md)
before interpreting the [recorded results](results/2026-09-19).

The inspected environment is `ssh root@192.168.1.253`, then `pct exec 101 -- bash`.
Probe sources and binaries are already in `/opt/aimee-ple-phase0` in that guest.
The commands below run **inside CT 101**. Python probes use only its standard
library. A compiler and the existing llama.cpp headers/libraries are required.

## Tokenization and layout

Copy these probe sources into `/opt/aimee-ple-phase0`, then:

```sh
cd /opt/aimee-ple-phase0
g++ -std=c++17 -O2 -I/opt/llama.cpp/include -I/opt/llama.cpp/ggml/include \
  tokenize.cpp -L/opt/llama.cpp/build/bin -lllama \
  -Wl,-rpath,/opt/llama.cpp/build/bin -o tokenize
python3 probe_phase0.py \
  --model-dir /opt/models/Qwen3.8-Flash-Next-UD-Q4_K_XL \
  --tokenizer ./tokenize --output q4-metadata-triggers.json \
  > q4-summary.json 2> tokenizer.log
python3 probe_phase0.py \
  --model-dir /opt/models/Qwen3.8-Flash-Next-UD-IQ4_XS \
  --tokenizer ./tokenize --output iq4-metadata-triggers.json \
  > iq4-summary.json 2> tokenizer-iq4.log
```

The GGUF parser intentionally supports little-endian v3 and the relevant common
row codecs. Unexpected formats fail instead of guessing. It is a local probe for
trusted model files, not a general untrusted-input parser. `layout_sha256` covers
the selected metadata (including overall quantization), dimensions, and type;
it is not a complete checkpoint or tokenizer fingerprint.

## Isolated overlay byte probe

The two upstream overlay source files were fetched unchanged from
[NLTM commit 8d5adc2](https://github.com/ortegaalfredo/llama.cpp-NLTM/tree/8d5adc2f2ff3ae715100257eeeb3bec61eb1726c).
They are MIT-licensed and remain external dependencies. To reproduce from a fresh
scratch directory, retrieve exactly this revision:

```sh
curl --fail --location --output llama-ple-overlay.cpp \
  https://raw.githubusercontent.com/ortegaalfredo/llama.cpp-NLTM/8d5adc2f2ff3ae715100257eeeb3bec61eb1726c/src/llama-ple-overlay.cpp
curl --fail --location --output llama-ple-overlay.h \
  https://raw.githubusercontent.com/ortegaalfredo/llama.cpp-NLTM/8d5adc2f2ff3ae715100257eeeb3bec61eb1726c/src/llama-ple-overlay.h
g++ -std=c++17 -O2 -Wall -Wextra \
  -I. -I/opt/llama.cpp/src -I/opt/llama.cpp/include -I/opt/llama.cpp/ggml/include \
  overlay_probe.cpp llama-ple-overlay.cpp \
  -L/opt/llama.cpp/build/bin -lllama -lggml -lggml-base \
  -Wl,-rpath,/opt/llama.cpp/build/bin -o overlay_probe
python3 - <<'PY'
import json
import subprocess
from pathlib import Path

t = json.loads(Path('q4-metadata-triggers.json').read_text())['table']
crossing = next(i for i in range(10000)
                if (t['data_offset'] + i*t['bytes_per_row']) % 4096
                + t['bytes_per_row'] > 4096)
results = []
for row in [t['sample_row'], crossing]:
    command = ['./overlay_probe', t['shard'], str(t['data_offset']), str(row),
               str(t['dims'][1]), str(t['bytes_per_row']), str(t['qtype']), '.']
    run = subprocess.run(command, text=True, capture_output=True, check=True)
    results.append(json.loads(run.stdout))
Path('overlay-results.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results, indent=2))
PY
```

The experiment assumes this host's measured 4 KiB page size. It maps the original
model read-only and overlays private pages in this process, using temporary patch
files in the scratch directory. The patch filenames do not use the model's
automatic sibling-discovery name. The test removes its temporary files.

Payloads are arbitrary bytes, not valid learned knowledge. Do not load them into
an inference process. Success establishes sampled byte restoration and process
isolation only. It does not test the server reload hook, mtime detection, GPU
copies, model-state invalidation, request isolation, or semantic forgetting.

## Recorded scope

`results/2026-09-19/` contains both model inspections, native vocabulary-loader
logs, run identity, and two overlay lifecycle results against Q4_K_XL's table.
No whole-model generation benchmark was run. The existing llama.cpp checkout
remained clean. No services, production schemas, or Aimee memory policies changed.
