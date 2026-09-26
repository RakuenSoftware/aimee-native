# Real-model vLLM streaming comparison

Gemma 4 12B Q8_0 GGUF, tensor parallelism 2, dual RX 7900 XTX, exact signed
release-5 client image. All 336 responses passed: 168 native and 168 text.
The fixed 32-record synthetic bank was delivered in full in both conditions;
56 groups query one, two or three facts, repeated for three rounds with alternating
condition order. These are repeated operational observations, not 336 independent
knowledge questions. No Qwen run was performed.

| Median | Native | Text |
|---|---:|---:|
| First nonempty streamed content | 66.15 ms | 377.24 ms |
| Complete HTTP response | 308.13 ms | 663.85 ms |
| Prompt tokens | 30 | 616 |
| Completion tokens | 6 | 6 |

Across paired requests, native avoided 98,448 prompt tokens: exactly 586 per
request, 95.1% of the median text prompt. Those memory positions are absent from
the conversation, including subsequent turns that would retain memory text.
Native state still occupies separate attention/device resources. These token
counts establish no API billing saving by themselves.

Native/text first-content medians by round were 65.14/372.87, 66.44/378.12 and
66.65/380.57 ms. First-content p95 was 74.53/387.38 ms; full-response p95 was
908.73/1371.93 ms. Full-response p99 was 1647.22/1580.46 ms: the native advantage
at the median does not establish dominance at every tail percentile. Text prefix caching is disabled by the shipped launcher in both conditions;
native device residency is retained between requests. Model load and preparation are excluded. HTTP scheduling, native
selection by fixture ID, inference and generation are included.

## Separate activation probes

| Bank | Cold median / p95 | Warm median / p95 |
|---|---:|---:|
| 3 records | 3.50 / 3.58 ms | 1.21 / 1.40 ms |
| 32 records | 31.44 / 31.79 ms | 10.26 / 12.04 ms |

Each bank has 20 fresh-process cold and 100 warm observations. `mincore` checks
coldness of the actual read source. Every tensor segment is compared after
activation. These rank-zero probes exclude model generation and setup; both ranks
are exercised by the full serving comparison. The approximately 0.56-microsecond
already-resident dictionary lookup is neither request-to-attention time nor the
8-microsecond cache reconciliation measured separately. The cold microsecond
activation target remains unmet.

[Protocol](../protocols/vllm-stream-validation-20260926.md) and
[append-only evidence](artifacts/vllm-stream-validation-20260926/) retain the exact
image, scripts, all observations, worker metrics, original logs and SHA-256 index.
`benchmarks/serving_validation/summarize.py` derives the aggregate and per-round
results. Test containers stopped normally; total run duration was 530 seconds.
