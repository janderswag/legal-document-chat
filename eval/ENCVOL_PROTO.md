# Encrypted-volume prototype — measured (encryption cycle, design doc §3)

_Run 2026-07-07 on the M4 Pro dev machine. Harness: `pipeline/bench_encrypted_volume.py`
(5 rounds; raw JSON in git-ignored `eval/results/encvol-proto-2026-07-07.json`). This is
the measured input the design doc §3 required before committing to per-matter vs
single-volume granularity. Budget: mount + first-query overhead < 500ms._

## Setup

Encrypted APFS sparse bundle (`hdiutil create -type SPARSEBUNDLE -fs APFS -encryption
AES-256`), hosting a copy of the 22MB / 5,114-chunk scale store (the largest store we
have). Each round: fresh attach (cold volume cache) -> first query through the
production retrieve() shape (connect + open_table + matter-prefiltered dense top-5,
fixed synthetic vector so no Ollama time pollutes the number) -> detach. Baseline: the
same first query against an unencrypted copy (page-cache warm after round 1 — the
per-round table keeps the cold/warm split visible).

## Results (5 rounds)

| metric | median | mean | max |
|---|---|---|---|
| attach (unlock + mount) | 443.8ms | 442.8ms | 454.0ms |
| first query, encrypted volume | 53.8ms | 59.4ms | 82.3ms |
| first query, plain baseline | 17.0ms | 16.6ms | 27.4ms |
| detach | 307.2ms | 260.9ms | 344.2ms |
| attach + encrypted first query | 496.9ms | 502.2ms | 536.3ms |

- **Overhead (median attach + enc-vs-plain query delta): 480.6ms — WITHIN the 500ms
  budget, but with only ~4% margin; the worst round's attach+query was 536ms.** Honest
  read: standalone, this sits at the budget line, not comfortably under it.
- **The margin problem disappears at app start**: the launcher already preloads models
  for seconds at startup; mounting concurrently there makes the effective added
  first-query latency ~0. The <500ms budget only binds if we mounted lazily per query,
  which nothing in the design requires.
- **Write path is free**: populating the volume with the 22MB store took 36.5ms vs
  35.1ms to the plain filesystem — APFS AES-256 overhead is negligible for ingest.
- **Steady-state query overhead is real but small**: ~37ms on the first query after
  mount (53.8 vs 17.0 median); subsequent queries converge (volume cache warms).
- Bundle create is one-time ~1.0s. Detach ~180-345ms happens at quit, invisible.

## Per-matter volumes: measured cost

Attach of five independent 512MB encrypted bundles: 313-416ms each (median 369.3ms),
essentially size-independent (hdiutil/DiskArbitration dominates). So per-matter
volumes cost ~0.4s x N at mount time: 10 matters ≈ 3.7s, 50 matters ≈ 18s at app
start, or a per-matter lazy mount that would push ~400ms into first access AND split
the single LanceDB table into per-matter stores — changing the retrieval/matter-
isolation query path that the non-negotiables require untouched.

## Time Machine

`tmutil addexclusion` on the sparse bundle works unprivileged and sticks
(`isexcluded` -> `[Excluded]`) — the existing D-71 `data_protection.py` pattern
extends to the bundle as-is. Defense in depth: even an unexcluded bundle backs up as
encrypted bands (ciphertext), unlike today's plaintext store files.

## Decision this measurement supports (recorded as D-73)

**Single encrypted volume for the whole KB store (design §3 "simpler v1"), mounted at
app start concurrently with the model preload, ejected on quit.** Per-matter DEKs
(Keychain-wrapped envelope) apply at the FILE layer to each matter's natives/export
tree. Crypto-shred (DEK destruction) then makes a matter's ORIGINALS irrecoverable =
NIST "Purge" for natives; derived chunks are deleted + compacted inside the encrypted
volume = better than today's "Clear" but stated separately and honestly on the
certificate (no blanket "Purge" claim). Per-matter volumes are rejected on measurement:
the N x 0.4s mount tax and the forced retrieval-path split are both worse than the
honest mixed certificate, and can be revisited if a true all-derived-data shred is
ever demanded.
