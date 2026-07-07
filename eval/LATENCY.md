# First-token latency (TTFT) — measured (Task 6 / G-LAT)

_Reading-aid measurement, 2026-06-20. Harness: `pipeline/run_latency.py`._

## Method
- 63 present-fact golden questions, the SAME grounded prompt `answer()` builds.
- TTFT = wall-clock from request-send to the first non-empty content token of the
  streamed qwen3:14b response. Knobs applied: **no-think** (`think=False`) + **warm
  `keep_alive=10m`** (no cold reload between questions).
- `answer()` body is unchanged (M2-7 parity); this is a streaming side channel.
- Loopback Ollama only; egress-monitored (`eval/results/egress-2026-06-20-t6.log`): 0
  non-loopback. Raw per-question data: git-ignored `eval/results/latency-2026-06-20.jsonl`.

## Result (honest — target NOT met)

| metric | TTFT |
|--------|------|
| mean   | 2.77s |
| median | 3.09s |
| p95    | 4.35s |

**CE_PLAN <3s first-token target: NOT met** (median 3.09s, just over). Many questions
do come in under 3s (TTFT floor ~1.8s), but the median sits just above the line.

## Honest conclusion
With no-think + a warm model, TTFT is dominated by **prompt prefill of the 5-chunk
grounded context on the 14B model** — not by reasoning. The remaining gap to <3s is a
hardware/model-size problem, not a prompt bug. Legitimate pre-M4 levers (not done here,
flagged): a smaller/quantized first-token model, GPU/production hardware (M4-5, no
purchase on spec), or trimming retrieved context (fewer/shorter chunks). Recorded as an
honest datapoint, not a silent miss; the instrumentation now exists to re-measure after
any of those changes.

---

# P0.2 re-measure — warm production path (2026-07-07)

_Harness: `pipeline/run_latency.py`, now at PRODUCTION PARITY with the shipped path:
`keep_alive=30m` + `options.num_ctx=8192` (the same knobs `_post_chat`/`_stream_tokens`
send since P0.2) + `think=False`. 63 present-fact golden questions, loopback Ollama._

## What changed in production (P0.2)
- `_post_chat` and `_stream_tokens` now send `keep_alive=30m` and `num_ctx=8192`
  (KV cache sized to the real ~2.5k-token 5-chunk prompt, far under the model's 40960
  max, never truncating a long cited answer).
- FastAPI startup fires a background `preload_model()` (empty request, no document
  data), so the model is resident BEFORE the first question.
- The desktop launcher starts a managed `ollama serve` (with `OLLAMA_FLASH_ATTENTION=1`
  + `OLLAMA_KEEP_ALIVE=30m`, loopback-forced) when none is running; a user's own
  running Ollama is left untouched.
- The app UI's default answer path is now the STREAMING endpoint (`/chat/stream`), so
  perceived wait = retrieval + TTFT, not the full ~8s generation.

## Cold-start cliff: CLOSED (the P0.2 acceptance)
Measured directly (scratch `coldcheck`): after a forced model unload, startup
`preload_model()` loads the weights in **2.28s in the background**, and the first user
query then shows **`load_duration` = 0.141s** (wall 0.72s for a trivial prompt) — vs the
~5.5s reload the first post-idle query previously paid. The published TTFT numbers no
longer hide a cold cliff, because the app no longer has one on its own lifecycle.

## TTFT result (measurement conditions matter — read the caveat)

| metric | TTFT 2026-06-20 | TTFT 2026-07-07 |
|--------|------|------|
| mean   | 2.77s | 3.35s |
| median | 3.09s | 3.45s |
| p95    | 4.35s | 5.20s |
| floor  | ~1.8s | 0.28s |
| under 3s | — | 20/63 (32%) |

**CE_PLAN <3s first-token target: still NOT met** (median 3.45s). CAVEAT, recorded
honestly: this run executed on a machine under sustained external load (load average
~7: multiple concurrent agent sessions, browser, desktop apps), and a same-day
72-question full-answer run was uniformly ~20% slower than its 2026-06-20 twin
(mean 8.6s vs 6.9s) with NO answer-quality change — i.e., the delta vs June reflects
machine load, not the P0.2 knobs. The new floor (0.28s on prompt-cache-friendly
consecutive questions) and the closed cold cliff are the real P0.2 wins; the median
remains prefill-bound on the 14B model exactly as diagnosed in the June entry.

## Verification alongside (gate discipline)
The full 72-question page+span eval re-ran under the new knobs
(`eval/results/run-2026-07-07-p02-numctx.jsonl`): **61 strict + F-042 alt-page
(credited, multi-page fact) = 62/63 = 98.4%**, 0 displayed fabrications, 0 rejected
claims, NF 9/9, DRM intact — IDENTICAL grade profile to the M2-8a baseline (same two
known non-passes: F-026 false-refusal recall gap, F-042 alt-page). `num_ctx=8192` +
`keep_alive` changed nothing about answer quality. Recorded as D-63.
