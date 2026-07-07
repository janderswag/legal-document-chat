# DECISIONS.md — Decisions already made

> Locked decisions carried over from `CE_PLAN.md` (finalized 2026-06-19, revised against the
> Manus AI Technical Validation Report). Section references point back into `CE_PLAN.md`.
> Changing any of these requires an explicit, recorded re-decision.

## Scope and safety

- **D-1 — Product is a cited-retrieval assistant, not an AI lawyer and not an autonomous agent.**
  Grounded search/summarize over the attorney's own docs; no advice, no actions. (CE_PLAN §1, §3)
- **D-2 — Retrieval is architecturally separated from action-taking.** The answering agent has no
  action tools and no network egress in v1. (CE_PLAN §3 principle #12)
- **D-3 — Dev uses fake/sanitized/public documents only;** real data is touched only at Milestone 6,
  onsite, on attorney-owned hardware, after written approval. (CE_PLAN §4 rule 1, §14)
- **D-4 — Local-only data-flow invariant.** No document bytes, embeddings, prompts, or answers leave
  the machine in confidential mode. Loopback binding only; no public port exposure. (CE_PLAN §4)
- **D-5 — Human verification is mandatory, not optional.** Every answer carries a citation and the
  "verify against source / not legal advice" footer. (CE_PLAN §10, §15)
- **D-28 — Synthetic pilot source documents live under ignored `documents/` paths; tracked `eval/`
  files may contain schemas, templates, and metadata but not document bodies.** Every document-like
  file — even synthetic/fake/sanitized pilot documents — lives under the git-ignored `documents/`
  tree (use `documents/synthetic_corpus/`), preserving the invariant that **document data is never
  committable by default**. The `eval/` tree is tracked and holds only the manifest schema,
  templates, and ground-truth metadata (`fact_id`, page, section, short `verbatim_span` snippets
  drawn from synthetic docs only, expected-absent topics, notes) — never a full source-document
  body and never any real client text. This supersedes the working-tree proposal to author the
  corpus under an unignored `corpus/` path, which would have made synthetic documents committable by
  default. (CE_PLAN §4 rule 1, §7.1; `.gitignore`)

## Sequencing

- **D-6 — Turnkey pilot first, before any custom code or capex.** Milestone 1 (Ollama +
  AnythingLLM) must prove citation accuracy and not-found refusal as the go/no-go gate. (CE_PLAN §14,
  §17 Task 0)
- **D-7 — Custom citation-grade build is deferred to Milestones 2–3,** only after M1 passes.
  (CE_PLAN §14)

## M1 measurement decisions (turnkey pilot)

- **D-29 — M1 citation accuracy is scored at FILENAME level, not page level (turnkey limitation;
  owner-approved 2026-06-19).** Empirically (M1-7c), AnythingLLM 1.14.1's desktop PDF parser flattens
  every page into one blob and emits **empty chunk metadata (no page field)** — so verifiable
  page-level citation is **mechanically impossible on the turnkey stack**, even from page-faithful
  PDFs (page breaks confirmed correct; parser is the bottleneck). Therefore M1 measures what the
  turnkey stack can prove: **answer-correctness + filename grounding + DRM right-doc/right-matter +
  not-found refusal.** `page_match` and exact-`verbatim_span` overlap are **dropped from mechanical
  M1 scoring** (page/section remain informational / optional human-read). **The product page-level bar
  is NOT lowered** — verifiable **page + mechanical span** citation is reassigned to **M2-3** (Docling
  page metadata + mechanical span verification), which is exactly where CE_PLAN already places the
  mechanical overlap check. So the M1 page-level miss is a **go/no-go input** (turnkey insufficient for
  the citation bar → the M2-3 custom build is justified), not a silent pass. Encoded in
  `eval/TEST_PLAN.md` §3.1/§4. (CE_PLAN §2 "filename + page/section … mechanically overlaps", §14,
  D-7, D-19)
- **D-30 — M1 not-found refusal is scored on substance, not exact wording (owner-approved).** The
  refusal safety gate passes when the system **declines + cites nothing**; the exact CE_PLAN §10 / D-5
  sentence ("I could not find this in the documents.") is **pinned as the product string** via the
  `m1-golden` workspace prompt and tracked as a separate UX flag `refusal_wording_exact` — a fixable
  UX check, never scored as a hallucination. **Refinement (owner-approved 2026-06-20):** the gate is
  scoped to the **absent topic** — NF passes iff it asserts no substantive answer to the *asked,
  absent* thing AND cites nothing *for it*; an accurate quote about a **different, real** clause is
  **logged as a quality note, not failed**. Because query mode **always** returns a `sources[]` array
  (retrieved chunks) even on refusals, scoring uses the citation the **answer asserts**, not raw
  `sources[]`. Encoded in `eval/TEST_PLAN.md` §3.2. (CE_PLAN §10, D-5)
- **D-31 — M1-10 air-gap (SC-6) is verified by egress monitoring, not physical disconnect
  (owner-approved 2026-06-20).** The full M1-10 run executes with networking **on** while a monitor
  (`lsof`/`nettop`/pktap) runs throughout and proves **zero non-loopback / zero document-bearing
  egress** — exactly CE_PLAN §2 SC-6's "network monitor confirms zero outbound carrying document
  content." Rationale: an AI-driven run needs the network, the corpus is synthetic, and monitoring is
  the CE_PLAN-specified proof. **Supersedes the earlier M1-EH "networking OFF" framing for M1-10
  only;** physical NIC-off air-gap remains the standard for **M6 real-data** work. (CE_PLAN §2 SC-6,
  §11)

- **D-32 — Present-fact `filename_match` is scored via AnythingLLM's returned `sources[]` citation
  panel (owner-approved 2026-06-20).** `filename_match` = the record's `.pdf` appears in the system's
  returned sources/citations (the mechanism by which the turnkey product surfaces citations) — the
  answer prose need not name the file. This is how both the Builder and the independent Tester graded
  M1-10; the **63/63 = 100%** present-fact metric stands on this reading. Asymmetry is intentional: NF
  "cites nothing" is scored on the **answer-asserted** citation, ignoring the always-present
  `sources[]` (D-30). (TEST_PLAN §3.1)
- **D-33 — M1-13 GO/NO-GO = PASS (filename level); M2-3 build authorized (owner, 2026-06-20).** The
  turnkey pilot met all four §4 gates on the synthetic corpus — citation **100%** (63/63, filename
  level per D-29/D-32), **0** fabricated, not-found refusal **100%** (9/9, D-30), **DRM 2/2** — under
  egress-monitored SC-6 (D-31). This is the CE_PLAN §14 go/no-go gate: turnkey local RAG + grounding +
  refusal are **validated**, and verifiable page+span citation is **proven impossible** on the turnkey
  stack → the **M2-3 custom pipeline is authorized** (FastAPI + LlamaIndex + Docling + Qdrant/LanceDB +
  reranker + mechanical span verification, D-13..D-20). **No production hardware purchase yet** (M4-5,
  after M2-3 validates). Carry-forward build inputs: verifiable page+span (D-19), DRM
  metadata-filter+reranker (D-18/D-16), latency tuning. See `BUILDER_STATE.md`. (CE_PLAN §14, D-6, D-7)

- **D-34 — M2 vector store = LanceDB (embedded), owner-chosen 2026-06-20.** Resolves D-14's
  Qdrant-primary / LanceDB-alternative in favor of **LanceDB** for the M2 build: embedded/serverless
  (no Docker, no server process), already proven on this machine (AnythingLLM's `m1-golden` ran on
  LanceDB), and sufficient metadata pre-filtering for single-tenant matter-scoping at D-26 scale.
  **Qdrant drops out of the deployment** (D-20); revisit only if M2-4 filtering or production scale
  demands it. Each chunk's payload carries `{source_filename, matter, page_number, section, char_start,
  char_end}` + chunk text (for M2-6); embed the **`embedding_text`** (SAC-prefixed, D-18). The LanceDB
  store contains document text → **git-ignored** (D-28). (CE_PLAN §6.4, D-14, D-20)

- **D-35 — M2 retrieval matter-scoping = explicit `matter` param (hard pre-filter); reranker
  sequenced separately (owner, 2026-06-20).** Matter-scoping is supplied as an **explicit `matter`
  filter param — no NLP inference from the question.** When provided, LanceDB **hard-pre-filters** rows
  to that matter **before** similarity (filter-then-search); absent → an explicit "search all matters."
  Rationale: inferring the matter from free text is the exact "right clause, wrong client" failure the
  system must prevent, and a solo attorney works within a known matter context; M2-3 showed SAC alone
  doesn't stop matter-agnostic cross-matter pulls. The **`bge-reranker-v2-m3` reranker (D-16) is
  sequenced as a separate step M2-4b** (its own owner-gated model install) after the proven-required
  pre-filter, so its lift can be isolated/measured — D-16 (reranker planned) is honored, just
  sequenced. (D-18, D-16, CE_PLAN §10)

- **D-36 — Reranker runs as a LOCAL in-process cross-encoder, not via Ollama (2026-06-20).**
  `bge-reranker-v2-m3` (D-16) is loaded directly via FlagEmbedding / sentence-transformers (Torch,
  already present from Docling) — **Ollama does not serve cross-encoder rerankers natively.** Weights
  are fetched once from HuggingFace (one-time, no document content); set HF/transformers **offline**
  after the fetch to prove air-gapped reranking. The reranker **reorders the matter-pre-filtered
  candidates** (M2-4) — it does not replace the D-18 hard pre-filter. Pin its revision/digest alongside
  the D-11 model pins and **measure its lift** vs the pre-filter baseline before relying on it. (D-16,
  D-35, CE_PLAN §10)
  **Refinement (2026-06-20, M2-4b measured):** the reranker **defaults OFF** (`rerank=False`) —
  measured **neutral lift** on the 6-doc corpus (ΔMRR ~-0.006, rank@1 48→46) does not justify its
  latency; it is **opt-in via `rerank=True`** and re-evaluated at real scale. **M2-5 answering builds
  on the `rerank=False` base path.** The pinned `RERANKER_REVISION` (in `reranker.py`) joins the
  central model-pin list alongside `qwen3:14b=bdbd181c33f2` and `bge-m3=790764642607` (D-11); a
  revision change forces re-eval.

- **D-37 — M2 answering/orchestration is hand-rolled; LlamaIndex dropped (supersedes the RAG part of
  D-13; owner, 2026-06-20).** The pipeline is built directly (PyMuPDF ingest → chunk + SAC → LanceDB →
  matter-filtered retrieval), **not** via LlamaIndex, for **full transparency of the
  claim→chunk→offset citation path** that mechanical span verification (D-19 / M2-6) requires — and
  because the M1 failure was an opaque framework's citation handling. M2-5 answering is a thin
  function: assemble matter-filtered (`rerank=False`) context with explicit per-chunk source labels →
  CE_PLAN §10 grounded + cite-every-claim + refusal prompt → `qwen3:14b` on system Ollama (D-11) →
  return the answer + the grounding chunk IDs/offsets. **This supersedes the "LlamaIndex (RAG)" portion
  of D-13;** the **FastAPI HTTP surface (D-13) still stands** for M2-7. (CE_PLAN §6.6, §10, D-13, D-19)

- **D-38 — Displayed citations are CHUNK-DERIVED, never model-asserted (2026-06-20, M2-5 Reviewer
  bug).** The filename + page shown to the user are taken from the **matched chunk's metadata**
  (`grounding_chunks[chunk_id].source_filename` / `.page_number`), **not** from the model's prose. The
  model's asserted citation is only a *pointer* to a chunk; the system replaces it with the chunk's
  verified filename+page, and (M2-6) mechanically verifies the cited span overlaps that chunk's
  offsets. **A model-asserted page is never trusted or displayed.** Fixes the M2-5 `_parse_citations`
  structured-tag branch (which emitted the model's page) — a **precondition of M2-6**. (D-19, D-29;
  M1 lesson: model-asserted pages were confidently wrong and unverifiable.)

- **D-39 — M2-8 re-instates the page+span citation bar that D-29 relaxed for the turnkey stack
  (2026-06-20).** Now that the custom pipeline delivers chunk-derived pages (D-38) + mechanical span
  verification (D-19, M2-6), the **M2-8 golden re-run scores at the original CE_PLAN §2/§11 bar**:
  present-fact citation = answer conveys fact **AND** chunk-derived `filename_match` **AND** `page_match`
  (chunk-derived page == manifest `page_number`) **AND** the cited span **mechanically verifies**
  against a retrieved chunk. **Displayed fabricated/mis-paged citations = hard-zero** — they must be
  rejected into `rejected_claims`, never shown (mechanically enforced by M2-6, not prompt-trusted). NF
  refusal stays the D-30 substance gate; DRM stays right-matter. Encoded in `eval/TEST_PLAN.md` §6; the
  M1 §3/§4 filename-level definition (D-29) remains the historical M1 record. (CE_PLAN §2, §11, D-19,
  D-29, D-38)

- **D-40 — M2-8 = FINAL PASS at the page+span bar (D-39); M2-8a normalization fix landed and
  independently confirmed (2026-06-20).** The M2-6 verifier normalization was extended to
  **`html.unescape` (decode HTML entities) + strip backslash-escaped quotes**, applied **symmetrically**
  to both the cited span and the chunk text (on top of collapse-ws / `-\n`→`-`), and the F-042
  **alternate-page** rule (§6.5) was encoded in the scoring/verification path. Targeted re-run flipped
  exactly **F-014** (`\"Landlord\"`) and **F-016** (`&quot;Premises&quot;`) from false-reject →
  verified (both chunk-derived **page 1**), with **zero** other facts changed (no regressions, no
  spurious verifications). **Independently reproduced by the Tester** (fresh `answer()` calls + a
  self-authored escaped-but-false span that still rejects → conservative-failure invariant HELD; the
  loosening recovers truthful escaped spans without enabling any false-accept). **Final metrics at the
  D-39 bar:** page+span citation accuracy **62/63 = 98.4% (≥95%)**, **0 displayed fabrications** (hard
  zero), **NF refusal 9/9 = 100%**, **DRM 2/2 = 100%** (no cross-matter). **F-026 is the lone genuine
  miss** — a retrieval-recall gap (model falsely refused a present fact whose page-1 caption occurrence
  was not surfaced), **correctly NOT force-passed**; revisit via top_k/reranker/chunking. Egress
  re-verified loopback-only (`eval/results/egress-2026-06-20-m2a.log`, 0 non-loopback, SC-6/D-31). The
  M2-3 custom pipeline thus **clears the verifiable page+span bar the turnkey stack proved impossible**
  (M1, D-29). Remaining M2 build tasks: **M2-7** (FastAPI loopback surface, D-13) and **M2-9** (Docker
  Compose, D-20). (CE_PLAN §2, §11; D-19, D-38, D-39)

- **D-41 — M2-7 HTTP surface = FastAPI + uvicorn, loopback-only, NO auth (owner, 2026-06-20).** Owner
  approved the **FastAPI + uvicorn** install into the pipeline venv (owner-gated, pinned versions
  recorded, one step — no other new deps). The M2-7 API is a **single-user loopback service**: bind
  **`127.0.0.1` only, never `0.0.0.0`** (D-4), and **no API auth** — the loopback bind is the boundary
  for the solo-attorney single-tenant v1 (D-23, D-25 no remote access in v1). The answering path keeps
  **no action tools and no network egress** (D-2); citations stay **chunk-derived** (D-38) and
  mechanically verified (D-19/M2-6). First slice: thin app over the existing `answer(question, matter)`
  (`POST /answer` → answer + chunk-derived citations + `rejected_claims`) + `GET /health`. (CE_PLAN
  §6.6, D-13, D-37 — FastAPI portion of D-13 stands though LlamaIndex was dropped.)

- **D-42 — Milestone 2-3 substantively COMPLETE: the custom pipeline delivers verifiable page+span
  citation the turnkey stack proved impossible (2026-06-20).** With **M2-8 = FINAL PASS** (D-40,
  page+span 62/63 = 98.4%, 0 displayed fabrications, NF 9/9, DRM 2/2) and **M2-7 done** (D-41, FastAPI
  loopback HTTP surface, Tester-confirmed: loopback-only bind, no-action routes, byte-identical
  `/answer` parity with `answer()`, 0 non-loopback egress), the M2-3 build goal (CE_PLAN §5–§11,
  D-13..D-19) is **met on the synthetic corpus**: PyMuPDF page-accurate ingest → chunk+SAC → LanceDB →
  matter-pre-filtered retrieval → grounded `qwen3:14b` answering → **chunk-derived (D-38) + mechanically
  span-verified (D-19) page+span citations** over a loopback FastAPI surface, all egress-monitored
  (D-31). **Still open in M2:** **M2-9** (Docker Compose deployment, D-20) — **deferred + owner-gated**
  (new install: Docker/Compose); do not start without explicit owner approval at the relay gate.
  **Carry-forward (not blockers):** F-026 recall gap, `answering._norm` escape-alignment, optional
  `openapi_url=None` hardening (all in `TASKS_M2.md` Risks). **Does NOT authorize** production hardware
  purchase (M4-5 — owner, after demo, D-21/D-22) or real data (M6 — onsite, written approval). The open
  pre-M4 items (latency/thinking-mode tuning; real-PDF section-heading robustness before M6) are owner
  forks, not started here. (CE_PLAN §11, §14; D-40, D-41)

- **D-43 — M2-9 deploy = single-service Docker Compose; container→host-Ollama via `host.docker.internal`;
  COMPOSE-ONLY loopback boundary (owner-chosen M2-9, 2026-06-20; Planner-verified against the artifacts).**
  Refines **D-20** for the LanceDB build: the Compose stack is **one service** — the FastAPI pipeline
  (`Dockerfile` + `docker-compose.yml`) — with **no Qdrant** (D-34), **no LlamaIndex** (D-37), **no UI**
  (deferred, not built), reranker **OFF** (D-36). **Ollama stays on the host** at `127.0.0.1:11434`
  (D-11), reached from the container via a **dedicated `LDI_OLLAMA_URL=http://host.docker.internal:11434`**
  env (deliberately separate from Ollama's own bind var) + `extra_hosts: host.docker.internal:host-gateway`;
  **Ollama's bind is unchanged and `OLLAMA_HOST` stays unset** (hard rule re D-11). LanceDB is **volume-
  mounted read-only** at runtime, **never baked into the image** (D-28/#7); the image COPYs only
  `pipeline/*.py` + serve-only deps (no doc bodies, no `.env`, no `.lancedb`). _Planner confirmed by
  reading `docker-compose.yml` + `Dockerfile`, not by the Tester's say-so._
  Three binding constraints recorded (each tied to a plan rule, not optional polish):
  - **(a) Loopback boundary is COMPOSE-ONLY.** The container CMD binds `0.0.0.0` **inside the container
    network namespace** (necessary for port publishing); the loopback guarantee comes from Compose's
    `ports: ["127.0.0.1:8000:8000"]`. A bare `docker run -p 8000:8000 <image>` would publish to
    `0.0.0.0` and expose the service **off-host — a hard-rule #4 / D-4 violation.** **Deploy via
    `docker compose` only; never `docker run -p` this image.** (Not executed in testing precisely
    because it would expose `0.0.0.0`.)
  - **(b) Portability caveat.** `host.docker.internal:host-gateway` is a **Docker-Desktop** convenience.
    On native Linux a `127.0.0.1`-bound host Ollama is **not** container-reachable without host
    networking / explicit gateway routing — reachability **and** egress (D-31) must be **re-proven**
    before any Linux/CUDA deploy (relevant to a future D-22 hardware path).
  - **(c) Egress posture.** Live run was egress-monitored (D-31): zero non-loopback (host loopback
    ingress `127.0.0.1:8000` + container→host Ollama landing on `127.0.0.1:11434`); the
    `eval/results/egress-2026-06-20-m2-9.log` is a **git-ignored, regenerable local artifact** (D-28),
    not committed. (CE_PLAN §6.8, §13; D-20, D-11, D-28, D-41; hard rule #4)

- **D-44 — MILESTONE 2-3 COMPLETE (2026-06-20).** All M2 build tasks are done and independently
  Tester-confirmed: M2-1…M2-6 (page-accurate ingest → chunk+SAC → LanceDB → matter-pre-filter →
  grounded answering → mechanical span verification), **M2-8 = FINAL PASS** at the page+span bar (D-40:
  62/63 = 98.4% ≥95%, **0 displayed fabrications**, NF 9/9, DRM 2/2; conservative verifier), **M2-7**
  (loopback FastAPI surface, D-41), **M2-9** (Compose deploy, D-43). **Result vs the plan:** the custom
  pipeline **delivers the verifiable page+span citation the turnkey stack proved impossible** (M1, D-29)
  and holds the CE_PLAN §2 **SC-6 zero-egress** posture throughout (egress-monitored, D-31) — the M2-3
  goal (CE_PLAN §5–§11, D-13..D-19) is **met on the synthetic corpus**. **What this does NOT authorize
  (still owner-gated, hard rules #1–#2 / D-3 / D-21–D-22):** production hardware purchase (M4-5, only
  after the attorney sees a demo; no purchase on spec) and any real attorney/client data (M6, onsite, on
  attorney hardware, after **written** approval). **Owner-deferred next-step options** (none auto-started
  by the relay): pre-M4 latency/thinking-mode tuning; M4-5 hardware decision; M6 real-PDF section-heading
  robustness validation (still synthetic). **Open carry-forwards (none blockers):** F-026 recall gap;
  `answering._norm` escape-alignment (fails safe); optional API hardening (`openapi_url=None`,
  validate-matter-before-embed); compose-only deploy guard/README; image leanness. (CE_PLAN §11, §14;
  D-40, D-41, D-42, D-43)

- **D-45 — SC-5 demo source-viewer UI built; "M2-3 complete" (D-44) reframed to capability-level after
  a CE_PLAN cross-reference exposed open M2/M3 acceptance gaps (2026-06-20).** A cross-reference of the
  build against **CE_PLAN §2 (SC-1..SC-7)** and the **§14 milestone acceptance** showed the internal
  "Milestone 2-3 COMPLETE" label (D-44) was scored on the **page+span eval only** and is narrower than
  CE_PLAN's M2/M3 acceptance. **Honest status:** the citation-grade *capability* is complete and proven,
  but these CE_PLAN acceptance items are **open**: **SC-2** (OCR of ≥5 image-only/scanned PDFs — the
  pipeline is born-digital only, `do_ocr=False`), **SC-1** (20–50 doc, multi-format corpus — we have 6
  born-digital PDFs), **hybrid dense+BM25 retrieval** (dense-only built; reranker off), **<3s
  first-token latency** (uninstrumented, ~7s/Q), and **SC-7** (redeploy-from-scripts proof). These are
  now tracked as the **M2/M3 acceptance-gap closeout** (`TASKS_M2.md`). **SC-5 is the first closed:**
  a thin, read-only **demo source-viewer UI** was added to the existing loopback FastAPI app — `GET /`
  (static page), `GET /matters` (store allowlist), `GET /source/{file}` (**path-locked** to
  `documents/synthetic_corpus/pdf`, synthetic only) — so a citation opens the original PDF **at the
  cited page** (`#page=N`), satisfying SC-5's "expose snippets **and** open the original at the cited
  page." **No new deps** (Starlette `FileResponse`/`HTMLResponse`); `/answer` untouched (M2-7 parity
  holds — prose cleanup is client-side display only); path-traversal rejected (tested first, TDD);
  read-only (no mutating routes); loopback-only. The viewer is a **local-run** surface (the corpus dir
  is git-ignored / absent in the M2-9 image by design). (CE_PLAN §2 SC-5, §14 M3; D-41, D-44)

- **D-46 — G-SC2 OCR path done (SC-2 at EXTRACTION level only); Tesseract is the local OCR engine
  (2026-06-20, Tester-confirmed).** Per-page text-vs-image routing (`extract_pages_ocr`): PyMuPDF
  text-layer pages stay on the fast path (born-digital output byte-identical), image-only pages route to
  **Tesseract** (`pytesseract==0.3.13` → system `tesseract` 5.5.2, `eng.traineddata` local — **no model
  download**, EasyOCR/RapidOCR explicitly not used; D-15 honored). Page boundaries preserved, per-page
  `ocr_failed` fail-loud flag (don't index garbage, §8). Proven on ≥5 synthetic 300-DPI image-only PDFs
  (git-ignored): all present-fact spans recovered at token-coverage 1.00 on their own page; zero network
  egress; live `.lancedb` + M2-8 artifacts untouched. **Scope boundary: SC-2 is met only at the
  extraction layer — OCR text is NOT yet chunked/embedded/retrievable**; true end-to-end "searchable"
  (SC-2) requires wiring OCR into ingest→index, sequenced with **G-SC1**. Validated on clean synthetic
  rasters, **not real scans** (re-validate at M6); two real-PDF routing edge cases logged (`TASKS_M2.md`
  Risks). **Does not move the CE_PLAN M2 acceptance gate** — that needs SC-1 + SC-2-integrated + the M3
  items. (CE_PLAN §2 SC-2, §8 step 3; D-15, D-45)

- **D-47 — M2/M3 gap-closure batch outcome: reds green, latency the lone honest yellow (2026-06-20,
  Tester-confirmed + Planner-verified).** All seven plan tasks
  (`docs/superpowers/plans/2026-06-20-m2m3-gap-closure.md`) landed as 7 per-task commits
  (`89c7c66`→`c2cc89f`); Planner verified the code/tests exist, the baseline `.lancedb` + M2-8 artifacts
  are byte-identical (untouched), and the new stores `.lancedb_full`/`.lancedb_hyb` are git-ignored (D-28
  holds). **Independently-verified SC scorecard:**
  - **SC-1** (20–50 doc multi-format, per-file report, idempotent) — 🟢 22 docs/4 types, idempotent,
    quarantine + `.error.txt`.
  - **SC-2** (OCR scanned → searchable e2e + robust) — 🟢 **at capability level**: an OCR'd page is
    span-verified-answerable; degraded/mixed/sparse routing all pass. **Real-scan final validation stays
    M6** (OCR conf 93–95% even on degraded synthetic renders; synthetic rasters ≠ real scans).
  - **§8 quarantine + logs** — 🟢 (`ocr_failed`→`needs_review`).
  - **M3 hybrid dense+BM25** — 🟢 implemented (native LanceDB FTS + RRF behind the matter pre-filter),
    **measured lift NEGATIVE at this 6-matter scale (−4 rank@1) → correctly default-off** (D-36 mirror;
    re-evaluate at production corpus scale).
  - **M3 `<3s` first-token latency** — 🟡 **NOT MET**: instrumented, independent median **~3.6s**
    (Builder 3.09s; either way a miss). `answer()` parity preserved. **Honest yellow** — the "production
    hardware fixes it" read (qwen3 prefill/thinking-bound on the M4 Pro) is a **hypothesis to validate on
    D-22 hardware**, not proven; the pilot-hardware target is unmet.
  - **SC-3/4/5** — 🟢 (M2-8 stands 62/63, 0 fabrications; G-SC5 viewer). **SC-6** — 🟢 (0 non-loopback
    across all task monitors). **SC-7** — 🟢 (live down→up→/answer→restore→down, compose-only, loopback).
  - **Plan deviation (accepted):** `tantivy` was **not** installed — LanceDB **native FTS** was used
    instead (fewer deps, same capability). Net new installs this batch: `python-docx`, `Pillow`(if
    missing). Pins unchanged (D-11).
  - **Process flags:** (a) the t2–t7 egress logs were first **committed empty**, then remediated with
    real samples — **going forward every network-bearing run must write real monitor samples** (carry-
    forward); (b) the earlier-milestone code (M2-7 `api.py`, M2-9 `Dockerfile`/`compose`, the SC-5 UI)
    is **uncommitted** in the working tree — a git-hygiene loose end to land.
  - **Precise gate reading:** the CE_PLAN §2 **"GO for attorney demo" gate is worded on SC-1…SC-7**, and
    those are all 🟢 → the demo-GO gate is met. The **`<3s` first-token figure is a §2 quantitative /
    §14-M3-acceptance target that is OPEN** — so M3 acceptance is not 100% complete; do not relabel
    M2/M3 "complete." Unlocks only the **owner** decision on CE_PLAN **Milestone 4** (attorney UAT). Does
    NOT authorize M4-5 hardware purchase (no purchase on spec, D-21/D-22) or M6 real data (written
    approval). (CE_PLAN §2, §14 M2/M3; D-15, D-36, D-40, D-41, D-43, D-45, D-46)

- **D-48 — SAM-style local UI COMPLETE (2026-06-20, Tester-confirmed + Planner-verified).** The 7-task
  SAM-inspired but **100% local/air-gapped** UI (plan: `docs/superpowers/plans/2026-06-20-sam-style-ui.md`)
  landed as 7 per-task commits (`77a3b88`→`0e7abdb`); Planner verified the commits + a clean tree. The
  Tester independently confirmed all 7 🟢: app shell + **local-only assets (no CDN)**; Matters (SQLite
  catalog, path-safe slugs, D-18); **Document Hub** (drag/drop upload → async `Parsing→Ready` ingest into
  the dedicated **`.lancedb_kb`**, status table, **safe delete locked to `documents/kb/`** — hard rule
  #5); matter-scoped **cited chat** + persisted history (chunk-derived D-38 + span-verified D-19; D-30
  refusal; no cross-matter leak); **retrieved-page thumbnails + cited-span highlight** (PyMuPDF, read-only
  source); rich answer render (markdown + source chips + Sources, **escape-before-render XSS guard**);
  **Settings privacy badge** ("100% local · 0 outbound", derived not hardcoded). **88 real egress rows, 0
  non-loopback;** the three eval stores + M2-8 artifacts **byte-identical** (all writes went to the
  git-ignored `.lancedb_kb`/`.kb_catalog.db`). **Product boundary held** — nav is exactly New Chat ·
  Matters · Document Hub · Chat History · Settings; no drafting/advice/actions/CDN/cloud. **Housekeeping
  (not blockers):** two clearly-labelled synthetic matters remain in the git-ignored live catalog
  (removable; no `DELETE /matters` route by design); no live `/app` screenshot captured yet. This is the
  **CE_PLAN Milestone-4 demo surface** — it does NOT by itself complete M4 (which also needs a user-guide
  + demo script + attorney UAT) and does NOT authorize M4-5 hardware (D-21/D-22) or M6 real data. (CE_PLAN
  §14 M4; D-2, D-18, D-30, D-38, D-41)

- **D-49 — OSS landscape evaluation (9 repos) → adoption roadmap (2026-06-21, owner-directed).** Deep
  source-level dive (not READMEs) into kotaemon, ragflow, docling, superwise/Legal_Document_Analyzer_AI,
  OssamaLouati/Legal-AI_Project, THEOLEX/legal_doc_processing, jamietso/Tabular_Review,
  freelawproject/bankruptcy-parser, glamboyosa/lawyergpt — each cloned to `/tmp`, cross-referenced vs our
  `pipeline/*.py`. Full note: **`docs/research/2026-06-21-oss-evaluation.md`**. **Headline:** we already
  run a full Docling conversion and discard ~95% of it (keep only `section_header` strings) — its
  TableFormer tables + per-element `ProvenanceItem` (page+bbox+charspan) are our biggest unused upgrade.
  **Adopt roadmap (owner-greenlit sequencing 1→3→2, transcripts a separate track):** (1) Docling tables +
  provenance; (3) clause-extraction panel (CUAD 41-clause taxonomy + legal 11-section "contract summary"
  prompt, span-verified); (2) tabular-review grid (doc×question, server-side over `answer()`+verifier);
  (4) transcripts page:line + Q/A chunking — net-new, brainstorm-first, **no repo solves it** (RAGFlow
  `qa.py` + Docling `PageChunker` + PyMuPDF line-coords are only partial skeletons). **Confirmed our
  moats — do NOT churn:** our mechanical span verifier beats every repo's grounding (RAGFlow `[ID:n]` no-
  entailment; kotaemon/Tabular_Review fuzzy-regex would false-accept); our RRF hybrid > kotaemon's concat;
  matter pre-filter + SAC + hand-rolling (no LlamaIndex/LangChain) all validated. **Skip:** GraphRAG, all
  server vector stores (Qdrant/ES/Infinity/pgvector), cloud LLM/ingestion, dead deps (PyPDF2/Wand/
  mlx_vlm). **Dep-cost flags:** HybridChunker→transformers+semchunk, CUAD→torch, spaCy auto-downloads
  (vendor for air-gap). Latency yellow (G-LAT) is untouched by this — Docling-MPS helps *ingestion*
  throughput, not first-token. (CE_PLAN §5–§10; D-15, D-18, D-19, D-34, D-36)

- **D-50 — Workstream M-ENRICH authorized; first task = Docling TableFormer table ingestion (2026-06-21,
  owner-approved).** Opens a post-M3 capability workstream (see `TASKS_M2.md` → M-ENRICH). **Owner gates
  cleared:** (a) one-time local fetch of `docling-project/docling-models` (TableFormer) **approved** —
  runs fully offline after, under the existing `DOCLING_ALLOW_MODEL_FETCH` gate; pin the model revision
  (D-11 style — a change forces table re-index); (b) table representation = **one Markdown table per
  table chunk**, carrying `page_number` (+ bbox provenance where available), large tables split with the
  header row repeated. **Scope discipline (mirrors the G-SC2 OCR pattern): first Builder task is the
  EXTRACTION layer only** (`extract_tables` → per-table `{source_filename, page_number, bbox, markdown}`
  on a synthetic table-bearing doc), test-first, **baseline `.lancedb`/M2-8 artifacts byte-identical**
  (no re-embed/re-eval), born-digital text path unchanged, loopback-only + egress-monitored. Chunk→embed→
  index→answer integration is the **follow-up** task. **Verifier interaction (must be handled, not
  weakened):** Docling `charspan` indexes Docling's own serialized text, NOT PyMuPDF page text — keep
  PyMuPDF as the span-verifier offset source-of-truth; table chunks are a NEW chunk type whose verbatim-
  span semantics the integration task must define so the conservative never-false-accept invariant (D-19/
  D-38) still holds. (CE_PLAN §6.3, §8; D-11, D-15, D-19, D-28, D-31, D-38, D-49)

- **D-51 — Tester independent cross-eval reconciled into the M-ENRICH plan (2026-06-21).** A second,
  independent 9-repo deep dive (Tester tab, same protocol) **converged with D-49 on all majors** (Docling
  under-use = top finding; tabular grid + transcripts = the two real new capabilities; our mechanical
  span verifier ahead of every repo; legal repos mostly thin cloud demos; skip cloud/heavy-infra/
  frameworks) — two independent passes, same conclusions. **Net-new adopted items:** (a) **`eyecite`**
  (Free Law Project, pure-Python offline) — extract/normalize case+statute citations to structured
  metadata → retrieve-by-authority (fills the structured-legal-field gap; D-49's agents missed it as an
  FLP sibling lib); (b) Docling **`OcrMac`** native-Vision OCR (zero weights, offline, faster on Apple
  Silicon) — STUDY; (c) **streaming-token SSE UX** — improves *perceived* latency (not first-token),
  Tier-3 UI. **Architectural decision (offset-routing):** NEVER mix PyMuPDF and Docling char-offsets on
  the same chunk (silently breaks span verification). **One canonical extractor per document** — PyMuPDF
  fast path for clean born-digital text (latency), heavy Docling path only for tabular/scanned docs. This
  governs T-TBL and sharpens D-50's verifier note. **Push-backs (NOT fully adopted):** (1) fuzzy
  span-verify fallback (kotaemon difflib) stays **strictly NON-GATING** — may render a "probable source
  (unverified)" UI highlight but **never** enters the verified set / flips a claim to displayed (else it
  breaks D-19/D-38, our moat); (2) the retrieval recall fix (top-k×N before rerank) is a **hypothesis**
  for F-026, measure don't assert — and the fuzzy fallback would NOT fix F-026 (recall miss, not
  normalization drift); (3) prefer ~free **logprob** answer-confidence over an extra LLM-as-grader
  round-trip. **OPEN OWNER FORK — sequencing:** owner pre-approved Docling-tables-first (D-50); Tester
  credibly argues clause-checklist-first (cheapest, attorney-legible, prose clauses don't depend on
  tables). Both arcs converge on the grid (clause questions = grid columns). Builder prompt **held**
  pending owner's sequencing pick + plan approval. (CE_PLAN §5–§10; D-19, D-38, D-49, D-50)

- **D-52 — T-CLAUSE (Contract Review clause checklist) COMPLETE end-to-end, Tester-confirmed +
  Planner-verified (2026-06-21).** First M-ENRICH feature, built as **one comprehensive Builder pass**
  (owner workflow, `feedback-builder-comprehensive-prompts`). **All five layers complete, no stubs**
  (independently Tester-checked): (a) 20-clause CUAD-informed taxonomy (`pipeline/data/clause_taxonomy.json`,
  our own phrasing, CC-BY provenance); (b) `pipeline/clauses.py` `extract_clauses(matter, doc_id?)` →
  3-status classify (**found** only with a span-verified chunk-derived citation / **potentially_missing**
  on D-30 refusal, non-citable / **not_confirmed** when prose returns but spans reject); (c) loopback API
  (`routes_clauses.py`: `/clauses/taxonomy`, `/clauses/review`; 405 on action verbs, 400 on unknown
  matter); (d) Contract Review UI panel (3 statuses, citation chips reusing `/kb/highlight`, distinct
  missing badge, `esc()` XSS guard); (e) tests at every layer. **Tester verdict GREEN ×6:** fresh core
  invocation (indemnification→found p3, arbitration→potentially_missing); live 20-clause review over
  `.lancedb_kb` = 10 found / 10 missing / 0 not_confirmed reproduced 3×, every found row span-verified +
  `/kb/highlight` PNG resolves; **never-false-accept held on every path incl. wrong-file doc_id
  post-filter**; **0 non-loopback** (67 PID-scoped samples, `eval/results/egress-2026-06-21-tclause-tester.log`,
  git-ignored); **159/159 suite OK**; **baseline `.lancedb`/`.lancedb_full`/`.lancedb_hyb` byte-identical**
  (sha256 `13b242de…`/`0df0525c…`/`51e13b31…`, mtimes 2026-06-20, no re-embed/no M2-8 touch). **No new
  install; product boundary held** (locate/summarize only). **Two yellows carried to T-TBL step-0 (not
  blockers):** (1) add the `doc_id` post-filter **regression test** (logic verified live, no permanent
  test); (2) **commit** the untracked T-CLAUSE files (recurring git-hygiene loose end, cf. D-47). **Process
  notes:** the KB demo matter slug is **`pemberton-demo`** (NOT the eval store's "Pemberton Logistics
  (Nimbus MSA)") — future review prompts must use the KB slug; and **egress monitors must be PID-scoped
  (`lsof -a -p PID -iTCP`)** — a system-wide sample is not pipeline proof (reinforces D-47; the Tester
  caught + corrected two invalid passes). (CE_PLAN §6/§10/§14; D-19, D-30, D-35, D-38, D-47, D-49, D-51)

- **D-53 — T-TBL (Docling TableFormer tables) COMPLETE end-to-end, Tester-confirmed + Planner-verified
  (2026-06-21).** Second M-ENRICH feature; tables/exhibits are now searchable + **span-verifiably citable**
  — the capability prose-only ingestion couldn't deliver. **All layers complete, no stubs** (Tester GREEN
  ×7): Docling **TableFormer** extraction (offline from local cache, **no fetch at runtime**) → per-table
  `{source_filename, page_number, bbox, markdown}`; **one Markdown table per chunk** (D-50) with
  **self-relative offsets** (`char_start=0..len(text)`, `[TABLE]` section tag) — the **offset-routing**
  resolution (D-51): table chunks use Docling-derived self-relative spans, prose keeps the **PyMuPDF** path
  **byte-identical**, **offsets never mixed**; `has_tables` gating runs the heavy Docling pass **only on
  table-bearing docs** (prose-only PDF → 0 tables / 0 `[TABLE]` chunks, verified); embed/index to a
  KB/scratch store (**eval baseline untouched**). **Live proof:** "2026 annual license fee" → **$132,300**
  with a span-verified chunk-derived citation on `exhibit.pdf` p2 (offsets 323–331) that opens the page in
  the source viewer; **fabricated `$999,999` and altered-digit `$132,400` both reject** (0 citations, "does
  not overlap chunk C1") — **never-false-accept holds for table chunks**. **PID-scoped egress 0
  non-loopback** (21 samples); **baselines byte-identical** (`13b242de…`/`0df0525c…`/`51e13b31…`, mtimes
  2026-06-20); **175/175 suite OK** (offline Docling + live Ollama). Step-0 also landed: the T-CLAUSE
  `doc_id` regression test + two commits (`371c46e` governance, `37fa31d` feature). **Carry-forwards (none
  blocking):** (a) **`TABLEFORMER_REVISION` is documentary-only** (`table_extract.py:28` pins `fc0f2d45…`
  but nothing asserts the loaded snapshot matches) → add a startup/ingest assertion vs the cached model
  commit so a silent model swap forces a re-index; (b) **audit canon standardized** (now recorded in
  RUN_STATE): egress-log line format + the canonical store-hash fold method; (c) **KB housekeeping** —
  synthetic demo matters accumulating in the writable git-ignored `.lancedb_kb` (`tables-demo`,
  `pemberton-demo`, + the two from D-48) → prune before any attorney demo. (CE_PLAN §6.3/§8/§14; D-11,
  D-15, D-19, D-38, D-47, D-50, D-51, D-52)

- **D-54 — Builder execution protocol hardened + M-ENRICH backlog scoped (2026-06-21, owner-directed).**
  Owner asked to give the Builder a **comprehensive backlog** with anti-laziness "senior-engineer" framing
  (PROGRESS.md checklist, complete every task, no stubs, "going slow is OK"). Adopted as the standing
  Builder protocol (extends `feedback-builder-comprehensive-prompts`), with **one critical hardening the
  generic template lacked: a `[GATE]` HARD-STOP exception to "never ask permission"** — the Builder must
  STOP and surface (not proceed) for any **new install/dep/model-fetch, real data, hardware, non-loopback
  bind, weakening the span verifier, or re-indexing/re-running the eval baseline**; it keeps grinding all
  *other* tasks. **Definition-of-Done encodes our invariants** (test-first; never-false-accept preserved;
  baselines byte-identical via the audit-canon fold; loopback-only + PID-scoped egress; no new install).
  **Backlog IN scope (buildable, synthetic/public, no gate):** T-GRID; small wins (`answering._norm`
  escape-align, `openapi_url=None`, compose-only deploy README, logprob confidence, **non-gating** fuzzy
  span fallback, streaming SSE); retrieval experiments (top-k×N/F-026, sentence-window) **on SCRATCH +
  measured** (baseline mutation/M2-8 re-run = `[GATE]`); real-PDF robustness (bankruptcy-parser techniques
  **reimplemented on PyMuPDF — no new dep**; public court-PDF fixtures). **Backlog items that are `[GATE]`
  on install:** `eyecite` (new pip dep) → flag, don't install. **HELD OUT of any Builder prompt
  (Planner/owner-gated, NOT laziness):** **M6 real data + M4-5 hardware** = hard safety gates, *never* a
  Builder task (hard rules #1–2, D-21/D-22); **T-TRANS transcripts** = brainstorm-first (design gate,
  page:line ripples into verifier+UI); **G-LAT latency** = hardware-hypothesis (D-22), instrument-only;
  **M4 UAT / `/app` screenshot** = attorney-gated / manual demo asset. (CE_PLAN §2/§12/§14; hard rules
  #1–#4; D-19, D-21, D-22, D-31, D-38, D-47, D-49, D-51, D-53)

- **D-55 — M-ENRICH comprehensive backlog COMPLETE, Tester GREEN + Planner closeouts applied + committed
  (2026-06-21).** One PROGRESS.md grind (D-54 protocol) delivered **T-GRID + B1–B6 + C1/C2 + D1** —
  Tester-confirmed **240/240**, never-false-accept holds across the grid, the streaming path, AND the
  non-gating fuzzy fallback; bounded concurrency (ThreadPool ≤4); no cross-doc/matter leak; eval baselines
  byte-identical; production egress **0 non-loopback**. **Highlights:** A0 `TABLEFORMER_REVISION`
  code-enforced + KB pruned to one clean `demo-matter`; `POST /grid` SSE doc×question matrix reusing
  `clauses._classify` (not forked); B1 `answering._norm` aligned; B2 `openapi_url=None`; B3 compose-only
  README; B4 logprob confidence (display-only); B5 fuzzy fallback ("probable/unverified" UI only, **never**
  enters the verified set); B6 streaming chat; D1 bankruptcy-parser techniques reimplemented on **PyMuPDF
  (no new dep)** + public court fixtures. **C1 result (F-026):** top-k×N(20)+rerank **RECOVERS F-026**
  (page-1 caption chunk None→rank 3) — hypothesis now **measured/confirmed**, but rank@1 on easy facts
  trades 5/8→4/8 (matches D-36 neutral-lift); **turning it on is baseline-affecting → owner decision, NOT
  self-adopted** (`rerank=False` stays). **C2:** sentence-window marginal at our chunk size (avg −13.8%
  context, span always retained) → **defer** (revisit with larger/real-PDF chunks). Both measured
  READ-ONLY, no re-embed/re-index/M2-8 re-run (all `[GATE]`). **`eyecite` correctly held `[GATE]`** (new
  pip dep). **Planner closeouts applied at record (Tester carry-forwards):** (a) added the canonical
  **CWD-independent** `scripts/baseline_hash.sh` (cd-into-store → invocation-independent) — this **re-pins
  the audit-canon baseline hashes to `537146cf…`/`d329c91e…`/`07f04972…`** (the prior `13b242de…` set was
  path-prefix-sensitive — the very cross-role divergence carry-forward (a) flagged; contents unchanged,
  representation stabilized); (b) removed the empty `documents/kb/tables-demo/` leftover; (d) the A0
  **import-time air-gap fix** (offline env moved to module import so a standalone `assert_model_revision()`
  makes zero egress — the lone yellow; 20 table tests green). Committed (feature + governance). (CE_PLAN
  §6/§8/§10/§14; D-19, D-36, D-38, D-47, D-49, D-51, D-53, D-54)

- **D-56 — Transcripts design done but BUILD DEFERRED; agent personality PARKED (2026-06-21, owner).**
  Brainstormed transcripts (page:line Cited Q&A) to a complete design (`docs/superpowers/specs/
  2026-06-21-transcripts-design.md`): born-digital full-size PDFs, page-based line-aware chunking, and a
  **keystone that keeps never-false-accept intact** — page:line is *derived from the verified char-span*
  via a per-line map, never model-asserted (D-38 extended page→page:line). **Decision: do NOT build on
  spec.** Critical finding: depositions already work today as ordinary Document-Hub uploads (grounded,
  verified, **page-level** cites — ~80% of the value for free); the feature adds court-grade **page:line**
  precision, valuable **only if the attorney is deposition-heavy**, and carries a real "confidently-wrong
  line label" risk. **Trigger to build:** a real deposition shows page-level isn't precise enough. Cheap
  interim option (not yet scheduled): strip the line-number gutter so it doesn't pollute retrieval.
  Separately, **agent personality** for attorney-facing comms is **parked as future work** (owner: "could
  be good… not important now"); when picked up it must stay tone-only and not erode the product boundary
  (not an AI lawyer / no advice, CLAUDE.md) or the grounded-verifiable posture. Both tracked in `TASKS_M2.md`
  → Future/parked. (CE_PLAN §3/§14; CLAUDE.md hard rules; D-19, D-38, D-52)

- **D-57 — Project OPEN-SOURCED as a public GitHub repo (2026-06-22).** Published to
  **https://github.com/janderswag/legal-document-chat** (slug `legal-document-chat`, **MIT**, public).
  **Pre-flight audit was clean:** no secrets/keys/tokens/`.env`/PII/real documents in the working tree OR
  across all 29 commits of history (document bodies, `.lancedb*`, `.kb_catalog*`, `eval/results/` were
  git-ignored from day one); only emails present are the GitHub noreply (commit author) + synthetic
  `.example` addresses → **no key rotation / no history scrub needed**. `.gitignore` hardened (credential/
  key patterns, `node_modules`, store guards). Public docs added: searchable README ("Document Parsing &
  Chat with Open-Source Models for Attorneys"), CONTRIBUTING (recruits RAG/parsing/local-model/legal-tech
  contributors), MIT LICENSE (+ PyMuPDF-AGPL & CUAD-CC-BY attribution notes). Description (privacy-first,
  attorneys, local LLMs, verifiable citations) + **12 topics** set; **5 good-first-issues** created.
  **Curation call:** dropped the third-party Manus validation PDF; **KEPT the relay/governance docs at
  root** (revised the earlier "relocate to docs/dev/" plan — moving them mid-active-relay would break tab
  restore; the transparent decision-record + multi-agent process is also a public-story asset). Topics
  deliberately exclude `langchain`/`nextjs`/`llamaindex`/`openai` — not used (hand-rolled RAG, vanilla-JS
  UI, local Ollama). Ongoing governance commits are now public by this choice. (CLAUDE.md hard rule #7;
  D-28, D-37)

- **D-58 — Desktop app distribution: phased launcher → one-click app, pywebview-first (2026-06-29,
  owner-directed; design captured).** Goal: a downloadable, double-click app (macOS + Windows) so users
  aren't forced to self-host via terminal/Docker. Full design + cited research:
  `docs/superpowers/specs/2026-06-29-desktop-app-distribution.md`. **Owner decisions:** (1) **phased A→B**
  — ship a cheap launcher first, full one-click app later; (2) **wrap, don't rewrite** — keep the entire
  Python pipeline + the mechanical citation verifier (the moat) untouched. **Key research findings (2
  cited passes):** a desktop wrapper solves only the window; the two real blockers are (a) freezing the
  heavy Python backend (Docling pulls multi-GB PyTorch → 2–5 GB installer, 3 build machines, no
  cross-compile) and (b) the external Ollama + ~10 GB models. **No comparable shipped app uses a Python
  backend** (LM Studio/Jan/GPT4All/Ollama/Msty/AnythingLLM all embed a native llama.cpp/Ollama engine +
  download models in-app on first run). **Framework call: pywebview/tray over Tauri** — our UI is already
  vanilla HTML/JS over loopback, so Tauri's Rust IPC adds complexity for no benefit; pywebview ships the
  same PyInstaller bundle with fewer moving parts (Tauri stays a fallback only if a native feel is
  needed). **Phase A** = launcher around the existing FastAPI (still needs Ollama; **unsigned OK, $0**;
  technical audience). **Phase B** = embed the engine as a sidecar (no separate Ollama install) +
  in-app/offline first-run model download + PyInstaller backend sidecar + **signed/notarized installers
  (~$220/yr: $99 Apple + ~$10/mo Azure)** for the attorney audience. **Non-negotiable lessons:** ship the
  engine not the model; download models in-app on first run; keep loopback-only + no telemetry + opt-in
  updates (the air-gap moat must survive — offer an offline model installer). Code-signing is a *trust
  tax* (removes "unidentified developer / unknown publisher" warnings), NOT a distribution toll — unsigned
  still downloads and runs. **Implementation is a separate packaging effort, owner-gated, not relay
  pipeline code.** (CLAUDE.md hard rules #3/#4; D-37, D-57)

- **D-59 — Desktop packaging v1 COMPLETE, Tester GREEN + committed (2026-06-29).** All three v1 pieces
  shipped + independently Tester-confirmed (commit `c0400cb`): (1) **macOS pywebview launcher**
  (`desktop/launcher.py`) — frees port, binds `127.0.0.1` only, health-checks, opens a native window,
  stops the child uvicorn on window-close (port freed, no orphan); (2) **in-app first-run wizard**
  (`routes_setup.py` + `static/setup.*`) — detects Ollama reachability + the pinned models (exact/`:latest`/
  base match; rejects `qwen3:13b` near-miss), shows install-Ollama + exact `ollama pull` steps when
  missing, redirects to `/app` when ready; local-asset-only, only setup-time outbound ref is
  ollama.com/download; (3) **landing page** (`site/`) — 3-download procedure, macOS CTA → Releases,
  "Windows coming soon", "100% LOCAL · NO CLOUD · NO TELEMETRY", demo placeholder; Pages workflow is
  **manual-deploy only** (no push trigger). **257/257**; eval baselines byte-identical; **install footprint
  exactly `pywebview` 6.2.1 + pyobjc** (no PyInstaller/py2app/signing tooling, no Windows/non-loopback
  artifacts). Pipeline + verifier untouched. **One yellow (non-blocking):** launcher orphans its child on
  a *hard* kill (SIGTERM/SIGKILL) vs window-close — self-heals via `free_port()` next launch; hardening =
  signal handler / process-group cleanup (carried to the v1.1 follow-up). Tester carry-forwards resolved:
  A0 HF-offline ordering fixed; `scripts/baseline_hash.sh` already tracked; empty `documents/kb/tables-demo/`
  removed. (D-58; CLAUDE.md hard rules #3/#4)

- **D-60 — Distribution reality: direct notarized download YES, Mac App Store BLOCKED by the Ollama
  dependency (2026-06-30).** **Direct download (notarized, Developer ID, $99/yr) — the planned Phase B
  path — works fine with Ollama:** no sandbox, so the app can spawn the Python backend, talk to Ollama on
  `127.0.0.1`, and pull models. **Mac App Store is a hard path because of Ollama:** MAS mandates the App
  Sandbox (a sandboxed app **cannot launch an external `ollama` binary or run Terminal commands**) AND
  requires apps to be **self-contained** (guidelines 2.5.2 / 2.4.5 reject apps that need the user to
  separately install other software / pull 10 GB to function). No major local-LLM app (Ollama's own app,
  LM Studio, Jan, GPT4All) ships on MAS for exactly these reasons — they distribute direct. **To ever go
  on MAS we'd have to drop external Ollama and EMBED the inference engine (llama.cpp), full-sandbox, in-app
  model download, no Terminal — the bigger "true one-click" Phase B+ effort.** **Monetization implication:**
  the App Store is NOT required to launch or to charge — sell the **direct-download build via license
  keys / own checkout** (no 15–30% cut, no sandbox); the owner's doc-count pricing idea (D-58) decouples
  from MAS. App Store = a much-later milestone gated on embed-the-engine. Windows Store is analogous but
  looser. **Sequencing:** launch direct-notarized first; MAS/Store later. (CE_PLAN §12; D-57, D-58, D-59)

- **D-61 — Public site rebrands to docuchat.app; brand palette = navy/light-gray/white + GOLD accent;
  domain wired on Cloudflare; Windows scaffolded-not-built (2026-06-30, owner-directed).** Owner bought
  **docuchat.app** on Cloudflare and supplied a logo (navy doc+chat mark + lock-shield). **Decisions
  (owner-picked via Planner):** (1) **Rebrand** the public `site/` from "Legal Document Chat / §" to
  **docuchat.app** (repo + app internal name stay `legal-document-chat` — renaming breaks links).
  (2) **Repalette** off the current oxblood-red editorial theme to the **60-30-10 rule: Navy 60% /
  light-gray 30% / white background / GOLD 10% accent** (owner chose gold over the logo's native teal →
  **the logo's lock-shield is recolored gold** so logo+site agree). (3) **Windows:** cannot be built or
  tested from this Mac (no PyInstaller cross-compile; needs the owner's Windows box + SmartScreen) →
  Builder **scaffolds** (PyInstaller `.spec` + build script + `desktop/WINDOWS_TEST.md` + launcher
  cross-platform fixes) and the owner runs it on Windows to produce `docuchat-setup.exe` for the Release;
  button stays "soon" until the `.exe` lands. (4) **Domain/deploy:** GitHub Pages was **never enabled**
  (404) and Pages can't serve an arbitrary `site/` folder → Builder adds a **GitHub Actions Pages deploy
  workflow** for `site/` + `site/CNAME=docuchat.app`. **DNS DONE by Planner via Cloudflare API** (zone
  `docuchat.app`, token used + wiped, not committed): apex + `www` **CNAME → janderswag.github.io,
  DNS-only** (grey-cloud so GitHub issues the cert); apex resolves to `185.199.108-111.153`. Planner
  finishes Pages custom-domain + Enforce-HTTPS **after** the deploy workflow's first run. (5) New page
  content: **Cal.com** "need help? book a call" (`cal.com/hawkify/janderswag`) + email
  `jacob.mm.anderson@gmail.com` + GitHub + **Product Hunt badge** (post: legal-document-chat-for-attorneys-open)
  + an OSS star/share/PR band + `at1.png` "overwhelmed attorney" problem illustration. **Phone number NOT
  published** (owner directive). **Copy:** strip em-dashes (owner standing pref) + broaden "solo attorney".
  Marketing `site/` only — pipeline/verifier/air-gap app untouched. (D-57, D-58, D-60)

- **D-62 — SEO/GEO/AEO program + deploy-approval rule + weekly GEO-pulse loop (2026-07-01).**
  **Deploy-approval rule (standing, owner directive):** on the marketing site, **customer-facing/visual**
  changes (layout, copy, visuals, OG share cards, visible content, blog posts) are staged on a **local
  preview for owner approval before production**; **machine-only** changes (robots/sitemap/llms.txt,
  canonical/meta/JSON-LD, tests, CI, backend/pipeline) **push straight to prod**. Deploy = push `main`
  (`site/**` triggers Pages). **SEO batch (Tester GREEN ×8):** Phase A **LIVE** (`2ddaff6`) = robots.txt
  (welcomes GPTBot/ClaudeBot/PerplexityBot/Google-Extended/CCBot) + sitemap.xml + llms.txt/llms-full.txt +
  canonical + Organization & SoftwareApplication JSON-LD; Phase B **HELD** (`b6364c0`) = OG/Twitter cards +
  1200×630 OG image + visible FAQ (10 Q&A) + FAQPage JSON-LD (byte-identical to visible) + comparison table
  + GEO stat copy — **awaiting owner visual approval on `127.0.0.1:8090`**, then Planner pushes. 288 tests,
  baselines byte-identical, app untouched. **Accuracy fix (`cbaa78d`, paired with Phase B):** live
  `SoftwareApplication.operatingSystem` was `"macOS, Windows"` (overstatement — no Windows build yet) →
  set to **`"macOS"`** until the `.exe` ships (brand ethos = never overstate; FAQ already honest re:
  Windows-soon / run-from-source). **Weekly GEO-pulse loop:** DONE by Planner — installed `seo-audit`/
  `schema`/`ai-seo` skills (gitignored `.agents/`), scheduled trigger `trig_01BVV4Gskw5NAqBpvUbm9UkL`
  (Mondays 14:00 UTC, fresh cloud session, opens a review **PR** never pushes prod, emails+pushes a report).
  **Owner-side amplifiers:** connect Google Search Console (supply the verification meta token), optionally
  rename the Product Hunt listing to "docuchat" for the official badge. (D-57, D-59, D-60, D-61)

- **D-63 — P0 speed: streaming is the DEFAULT answer path + warm, right-sized production
  inference (2026-07-07, gated re-run PASSED).** (a) The app UI now answers via **POST
  /chat/stream** (SSE): retrieved chunk-derived passages render FIRST (a dimmed, non-clickable
  "Reading these passages" block — candidates, never presented as citations), tokens stream over
  them, and the `done` event re-renders with citations from the UNCHANGED verifier run on the
  COMPLETE text (never a partial; D-19/D-38 preserved). (b) Production Ollama calls
  (`_post_chat`/`_stream_tokens`) send **`keep_alive=30m`** + **`options.num_ctx=8192`** (KV
  sized to the real ~2.5k-token 5-chunk prompt; never truncates); FastAPI startup fires a
  background **`preload_model()`** (empty request, zero document data); the launcher starts a
  managed **`ollama serve`** (`OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KEEP_ALIVE=30m`,
  loopback-forced) only when none is running — a user's own Ollama is never touched. **[GATE]
  discipline:** `num_ctx`/`keep_alive` are model-affecting → full 72-question page+span re-run
  (`eval/results/run-2026-07-07-p02-numctx.jsonl`): **62/63 = 98.4% (F-042 alt-page credited),
  0 fabrications, 0 rejected claims, NF 9/9, DRM 2/2 — grade-identical to the M2-8a baseline.**
  Cold-start cliff CLOSED: post-preload first query `load_duration` 0.141s (vs ~5.5s reload).
  TTFT re-measured at production parity: median 3.45s under heavy external machine load
  (June baseline 3.09s on a quiet box; same-day full-answer twin run ~20% slower with
  identical grades → delta is load, not the knobs). <3s target still honestly NOT met;
  floor 0.28s. Full numbers + caveats: `eval/LATENCY.md`. (D-19, D-38, D-40)

- **D-64 — P1 onboarding: first-value with zero setup (2026-07-07).** (a) **Sample matter
  seeding:** on a truly FRESH install (zero matters), the app seeds "Sample Matter (Demo)" with
  three PyMuPDF-generated, banner-labelled SYNTHETIC PDFs and ingests them through the normal KB
  path once the local models are ready (bounded background wait) — a brand-new user reaches a
  span-verified cited answer with no setup. Never runs when any matter exists (cannot touch or
  shadow user data; D-35 isolation untouched). Sample docs are generated at seed time (no binary
  fixtures in git; hard rule #1 synthetic-only). (b) **Guided first-run:** the Chat empty state
  offers one-click suggested questions on the sample matter and a 3-step guided path (create
  matter -> add document -> ask) when no matters exist; "Choose a matter first" dead-ends are
  gone — the active matter persists in localStorage (slug only), is re-validated against
  /matters, and defaults to the first (preferring sample) matter. (c) **The setup wizard is now
  a DOER:** POST /setup/pull streams the local Ollama's /api/pull as SSE into a real in-app
  progress bar (allowlisted to the two pinned models only — never a caller-supplied name), plus
  Tesseract detection and free-disk notices. The one deliberate setup-time download (the same
  model pull the wizard previously told the user to type into a terminal); zero terminal
  commands remain in the happy path; the query/document path stays loopback-only. (D-58, D-63)

- **D-65 — P2 packaging: frozen-launcher fix + one-command build kits; certificates are the
  only missing input (2026-07-07).** (a) **Frozen-uvicorn bug FIXED:** a PyInstaller-frozen
  launcher would have spawned ``sys.executable -m uvicorn`` — i.e., relaunched ITSELF — on both
  platforms; when ``sys.frozen`` the server now runs in-process (``uvicorn.Server`` in a daemon
  thread; nothing to orphan), unit-proven on a live port. (b) **Managed Ollama:** the launcher
  starts ``ollama serve`` as a reaped child (flash-attention + keep_alive env, loopback-forced
  bind) when none is running, preferring a SILENTLY BUNDLED binary inside the frozen app
  (``resources/ollama``, fetched by the build script with ``BUNDLE_OLLAMA=1`` — MIT-licensed);
  a user's own running Ollama is never touched. (c) **macOS kit:** ``desktop/build_macos.spec``
  (.app bundle) + ``desktop/build_macos.sh`` (one command: bundle -> sign w/ hardened runtime +
  ``desktop/entitlements.plist`` -> DMG -> notarize -> staple), producing an UNSIGNED testing
  DMG when cert env vars are absent. (d) **Blocked on purchases only:** Apple Developer
  Program + Developer ID cert + notarytool profile (macOS), Azure Trusted Signing or OV cert
  (Windows) — exact owner checklist in ``desktop/SIGNING.md``; Windows build still runs on the
  owner's Windows box (PyInstaller does not cross-compile). Site claims stay honest until an
  artifact actually ships (D-62 accuracy ethos). (D-58, D-60, D-61)

- **D-66 — Council held: scale/transcripts/trust; roadmap PROPOSED, adoption owner-gated
  (2026-07-07).** Six independent agent reports (3 adversarial code audits with measured numbers,
  3 cited market sweeps) synthesized in `docs/council/2026-07-07-council-scale-transcripts-trust.md`
  (verbatim evidence in `docs/council/2026-07-07-reports/`). Headline findings: (a) **scale bomb**
  — `retrieval.py:36` materializes the entire store per matter-scoped query (measured 15.6s +
  4.7GB @100k chunks; unusable at ~90 docs; ~5-line fix, [GATE] re-run required); brute-force
  vector search itself is FINE to 500k chunks (96ms p50 measured — no ANN needed at target);
  (b) ingest shares the request thread pool (bulk upload starves /chat) and is uninstrumented;
  (c) dense-only retrieval already fails exact-term attorney queries at 50 chunks (measured);
  hybrid+rerank+/search endpoint gated on a new 1k-5k-doc per-query-class scale eval;
  (d) transcripts effectively unsupported (no page:line, .txt = one page, .ptx rejected) while
  the site claims "exact line" — copy fix owed; verifier substrate IS transcript-ready (derive
  page:line from verified offsets); (e) security proof gaps: unauthenticated Ollama + no
  TrustedHost/CSRF, plaintext at rest, no backup exclusions; at-rest encryption per matter →
  crypto-shred → retention tier (Rules 1.15/1.16, NIST 800-88r2); (f) market: the
  local+solo+legal+mechanically-verified cell is EMPTY; Heppner (S.D.N.Y. 2026) + 9th Cir.
  sanctions opinion + NY Part 161 are the demand events; $20-50/mo legal slot empty; top threat
  is free OSS, not incumbents; docuchat.io naming collision needs an owner call. Proposed
  sequence: Move 0 scale bombs + honesty patch → Move 1 retrieval-at-scale gated on the scale
  eval → Move 2 transcript engine → Move 3 trust pack → Move 4 retention product → Move 5 market
  motion. Non-negotiables reaffirmed: verifier + matter isolation byte-identical; claim ladder
  rungs 1-2 only ("verified" = quote fidelity + existence, never legal correctness). (D-63,
  D-64, D-65)

- **D-67 — Council roadmap ADOPTED as sequenced; name kept; product stays free (owner,
  2026-07-07).** The D-66 Move 0-5 order is adopted for execution: scale bombs + honesty patch →
  retrieval-at-scale gated on the new scale eval → transcript engine → trust pack → retention
  build → market motion. **Name:** "docuchat" is kept for now despite the docuchat.io collision
  (revisit before paid launch marketing). **Pricing:** free for now — no pricing page, no
  paywall, no license-gating work this cycle; the Move 4 retention build ships as product
  capability, monetization deferred. Explicitly DEFERRED from this cycle (from the council
  evidence, not lost): record cite-checker for drafts, chronology extractor, contradiction-
  candidate finder (transcript F5), medical-record/PI mode, privilege-log metadata tables,
  Bates-aware exhibit search, signed auto-update channel, SBOM, third-party pen test +
  attestation, SOC 2 / ISO 42001 roadmap, ethics-mapping page, small-model graceful tier,
  independent benchmark submission, Windows build execution (owner's box), cert purchases
  (owner). (D-66)

- **D-68 — Move 0 executed: scale bombs closed + honesty patch (2026-07-07, gates PASSED).**
  (a) **Allowlist bomb (0a):** the matter allowlist is now a matter-COLUMN-only scan cached by
  LanceDB table version (any write invalidates) — replacing the full-store
  ``to_arrow().to_pylist()`` materialization at retrieval.py:36/:28 that measured 15.6s + 4.7GB
  per query @100k chunks. Validation semantics unchanged (allowlist = matters present in the
  target store; D-18 ``prefilter=True`` untouched). **Acceptance: matter-scoped retrieve() warm
  p95 = 191ms on a synthetic 150k-chunk store** (~130ms of it question embedding). **[GATE]:
  full 72-question re-run grade-IDENTICAL to the same-day baseline** (61 strict + F-042 alt-page
  + F-026 known false-refusal + NF 9/9, 0 fabrications, 0 rejected claims). (b) **Serialized
  ingest (0b):** a single dedicated worker thread + queue (ingest_worker.py) replaces sync
  BackgroundTasks on the request pool; uploads enqueue instantly (status "queued"); worker skips
  docs deleted while queued; **interactive priority** — chat routes mark activity and the worker
  defers jobs while a chat is recent, because bulk embedding measurably slows generation on
  shared local compute. **Acceptance: 300-doc bulk ingest, all ready, /chat during ingest median
  4038ms vs idle 4026ms, p95 5924ms (< 2x idle).** (c) **Instrumentation (0c):** per-stage ingest
  timings logged (extract/embed_write/tables), queue depth + in-flight stage surfaced in the Hub
  via GET /kb/ingest/status (allowlisted deliberately), ``table.optimize()`` every 50 ingests
  (store previously never compacted). (d) **Honesty patch (0d, site, HELD for owner preview):**
  "exact line" claims scoped to "exact page and passage" until transcript page:line ships (D-66
  finding: untrue in every input format today); scanned-corpus "ingest overnight" expectation
  added to the OCR FAQ (visible + JSON-LD kept byte-identical). **Process note (honest):** the
  first gate run inherited run_m28.py's hardcoded output path and OVERWROTE the June 20 raw
  results jsonl (git-ignored; graded conclusions preserved in tracked grades-2026-06-20-m2.md);
  replaced the copy-and-sed pattern with parameterized ``run_golden.py`` that refuses to
  overwrite existing results. (D-66, D-67)

- **D-69 — Move 1 executed: retrieval at scale, measured; BEST-EVER gate 63/63
  (2026-07-07).** (a) **Scale eval built and standing** (`build_scale_store.py` +
  `run_scale_eval.py` + `eval/SCALE_EVAL.md`): 5,114 chunks through the PRODUCTION chunker, 50
  large matters (~75 chunks) with same-genre distractors, 113 questions stratified by query
  class. (b) **The data reversed two plan assumptions, adopted as measured:** hybrid stays OFF
  by default (raw-question BM25 costs paraphrase 12pts for +2 golden) and the reranker stays
  OFF (post-repair it can only demote: 98→95). The big lever was CHUNKING: (c) **1d schema
  repair** — production `_chunk_pages` is now section-aware with the full
  `[Matter | Type | Section]` SAC; `document_type`/`provenance`/`doc_date` added to the store
  schema (provenance squatting ended); golden recall@5 under production chunking went 81%→98%
  (pool 100%; ~93%→98% after netting out an eval matter-mapping bug found and fixed —
  honest attribution in SCALE_EVAL.md). `add_chunks` fail-louds on pre-1d stores;
  `reingest_kb.py` migrates (dev KB migrated). (d) **1b refusal second pass:** ONE retry on
  refusal with top_k=10, candidate_k=100, hybrid + ANCHOR-fed FTS (numbers, quoted strings,
  prefixed ids, proper nouns extracted from the question; `fts_query` param added to
  retrieve()); adopted only if span-verified non-refusal — a refusal can upgrade to a verified
  answer, never to an unverified one (verifier byte-identical). Streaming emits
  `second_pass` + fresh `sources`; refusals keep near-miss passages visible as explicitly
  unverified leads. (e) **1c GET /search:** retrieval-only search — exhaustive "every mention"
  mode with TRUE totals and labeled truncation + BM25 mode with a version-fresh FTS index
  (staleness footgun closed); matter allowlist validation identical to retrieval; new Search
  view in the app; route allowlisted deliberately. **[GATE]: 63/63 (62 strict + F-042
  alt-page) — the second pass RECOVERED F-026, the false refusal open since D-40; NF 9/9
  still refuse; 0 fabrications; 0 rejected claims.** 331 tests green. (D-66, D-67, D-68)

- **D-70 — Move 2 executed: the transcript engine (2026-07-07).** T-TRANS un-deferred (D-56
  trigger = owner roadmap adoption D-67), extended beyond the reserve design to ASCII .txt and
  speaker metadata. (a) **Ingestion:** user-designated at upload (`doc_type=transcript`, never
  auto-detected; catalog gains `doc_type` + a `transcript_lines` sidecar). PDF gutter parsing is
  GEOMETRIC (words binned by baseline y) — survives producers that emit the line number and the
  testimony as separate text objects, where plain-text extraction hides the gutter. ASCII pages
  split on form-feed or "Page N" headers. Gutter stripped from chunk text (embeddings
  de-polluted); line maps index the CLEAN page text, the same text chunks carry. (b) **Chunking:**
  one chunk per transcript page (a Q is never split from its A within a page); speaker labels and
  the prior page's tail ride in `embedding_text` ONLY — never citable text, and display never
  attributes a quote to a parser-guessed speaker. (c) **THE TRUST RULE:** page:line citations are
  DERIVED by mapping VERIFIER-CONFIRMED span offsets through the line map (verifier
  byte-identical; D-38 extended page→page:line). Ambiguous spans (same text twice on a page,
  the "Yes." trap) get NO line range — precise or absent. Condensed 4-up sheets FAIL LOUD at
  ingest with a clear reason (a confidently wrong 45:12 is worse than no ingest). (d) **Digest
  (2d):** POST /transcripts/{id}/digest — map-reduce over ALL pages (~10/batch, SSE progress),
  each bullet INDIVIDUALLY re-verified against its batch grounding, unverified bullets dropped
  and counted, the reduce step only groups/orders (generates no text), coverage stated ("built
  from all N indexed pages" — the top-k silent-partiality failure is structurally excluded);
  Word export as a Topic|Verbatim|Cite table (python-docx, already pinned in requirements).
  E2E proven live: chat answer cites p.4:14 on a synthetic depo; digest surfaces the planted
  fact with page:line; fabricated spans still yield zero citations. 345 tests green. Golden
  gate not re-run for Move 2 itself: answering/verifier/retrieval untouched (additive routes +
  ingest path only); the Move 1 gate (63/63) remains the standing baseline. (D-56, D-66, D-67,
  D-69)

- **D-71 — Move 3 executed: trust pack v1 (2026-07-07).** Loopback is not a security boundary;
  the app now proves it: (a) **API guards** — TrustedHostMiddleware (local hostnames only; kills
  DNS rebinding, where the attacker's domain resolves to 127.0.0.1) + an Origin guard rejecting
  state-changing requests whose browser Origin is non-local (kills cross-site POST/DELETE);
  the app's own same-origin requests and non-browser clients are unaffected; both proven by
  attack-shaped tests. (b) **Ollama hardening** — the launcher refuses to START an Ollama below
  0.17.1 (CVE-2026-7482 "Bleeding Llama", CVSS 9.1) with a clear upgrade message (fail-open only
  when the version is undeterminable), and sets OLLAMA_ORIGINS to the app origin (Ollama's
  default allows 0.0.0.0 — the 0-0-0-0-day/rebinding surface); a user's own Ollama is never
  touched. (c) **Supply chain** — the wizard's pull now verifies the D-11 pinned digests after
  download (the Ollama registry has no publisher signing); a digest mismatch is an error event,
  never a done. (d) **Backup/index leak reduction** — Time Machine exclusions + Spotlight
  markers applied to the KB store, document copies, and catalog at startup (idempotent,
  macOS-only, log-never-block), REPORTED in Settings by store name (the no-path status contract
  caught and fixed a path leak in the first cut); honest scope: interim until Move 4 at-rest
  encryption. (e) Settings surfaces the hardening posture from real state. Site trust page +
  security.txt ride on the site-preview branch (owner preview). 358 tests green. (D-66, D-67)

- **D-72 — Move 4 executed: retention primitives shipped; per-matter encryption DEFERRED by
  design (2026-07-07).** Design doc: `docs/2026-07-07-retention-encryption-design.md`. SHIPPED:
  (a) **legal holds** — first-class, reasoned, self-logging; an active hold 409s disposition AND
  single-document deletes (FRCP 37(e) preservation); (b) **export-everything** — one zip per
  matter: original natives + full chat threads with citations + catalog manifest (checksums) +
  the matter's audit slice (Rule 1.16(d) surrender BEFORE disposal, enforced in the flow);
  (c) **disposition + HONEST certificate** — removes chunks (store delete + compaction), line
  maps, threads, catalog rows, managed copies (still structurally locked to documents/kb/);
  emits a Certificate of Disposition modeled on NIST SP 800-88r2 App. C whose method is stated
  as **"Clear"** with explicit caveats (OS snapshots/backups outside app control) — NEVER
  "Purge" until cryptographic erase actually ships; (d) **hash-chained append-only audit log**
  (RFC 6962-style) covering hold/release/export/disposition, locally verifiable
  (/retention/audit/verify) — tampering with any entry breaks the chain, proven by test.
  Matters view UI: hold/export/dispose with double-confirm + certificate download. DEFERRED
  with rationale (design doc §4): per-matter envelope encryption (Keychain master key, DEK
  wrapping, SQLCipher catalog, encrypted-volume Lance stores) and the crypto-shred upgrade —
  key-custody mistakes on client data are unrecoverable and need their own focused cycle with a
  migration rehearsal; the trust page states the honest current posture. Full lifecycle
  acceptance test green (design §5). 359 tests green. (D-66, D-67, D-71)

- **D-73 — Encryption granularity MEASURED and decided: single encrypted volume + per-matter
  file-layer DEKs (2026-07-07).** The design-doc §3 prototype ran (`pipeline/
  bench_encrypted_volume.py`, writeup `eval/ENCVOL_PROTO.md`): encrypted APFS sparse bundle
  hosting the 22MB scale store — attach median 443.8ms, first-query overhead vs plain +36.8ms,
  total 480.6ms = within the 500ms budget but with only ~4% margin (worst round 536ms); write
  overhead negligible (36.5ms vs 35.1ms for a 22MB copy); per-matter volumes measured at
  ~369ms/volume attach = an N x 0.4s mount tax that would also split the LanceDB store and
  touch the untouchable retrieval/matter-isolation path. DECIDED: one encrypted volume for the
  whole KB store, mounted at app START concurrently with the model preload (absorbing the
  ~0.5s; no lazy per-query mount), ejected on quit; per-matter DEKs (Keychain-wrapped,
  AES-256-GCM envelope) encrypt each matter's natives/export tree at the file layer;
  crypto-shred destroys the DEK -> natives = NIST "Purge (cryptographic erase)", derived
  chunks = delete + compaction INSIDE the encrypted volume, stated separately on the
  certificate — no blanket "Purge" claim. Time Machine: `tmutil addexclusion` sticks on the
  bundle (D-71 pattern extends as-is); unexcluded bands would be ciphertext anyway (defense in
  depth vs today's plaintext store). (D-71, D-72)

## Stack — pilot (Milestone 1)

- **D-8 — Model runtime: Ollama** (pilot and production). OpenAI-compatible local API, Metal
  acceleration, serves both chat and embedding models. (CE_PLAN §6.1)
- **D-9 — Pilot UI: AnythingLLM.** Chosen over Open WebUI for lowest hallucination (6%) and the best
  out-of-the-box filename + page citations in the May 2026 benchmark. (CE_PLAN §6.2, §16 Q3)
- **D-10 — Chat model: `qwen3:14b`** (alt: Mistral Small 3.1 24B). Disciplined grounded RAG that
  degrades gracefully when evidence is missing. (CE_PLAN §6/§12, §16)
- **D-11 — Embedding model: `bge-m3` via Ollama,** chosen for native hybrid dense + sparse support;
  to be validated against our own legal golden set (not MTEB rank) before locking. Pin the id; a
  change forces a full re-index. (CE_PLAN §6.5)
- **D-12 — Pilot deployment: native macOS apps, no Docker.** (CE_PLAN §6.8)

## Stack — production (deferred, recorded for context; do NOT build in M1)

- **D-13 — Orchestration: FastAPI (HTTP surface) + LlamaIndex (RAG).** (CE_PLAN §6.6)
- **D-14 — Vector DB: Qdrant** (best metadata filtering for matter scoping); LanceDB is the
  embedded server-less alternative. (CE_PLAN §6.4)
- **D-15 — Parsing/OCR: Docling + PyMuPDF, Tesseract fallback.** PyMuPDF routes text-vs-image; born-
  digital via PyMuPDF normalized through Docling; image-only via Tesseract. (CE_PLAN §6.3)
- **D-16 — Reranker: `bge-reranker-v2-m3`,** planned (not "only if measured"). (CE_PLAN §10)
- **D-17 — Storage: lifecycle folders** (`inbox`/`processed`/`failed`/`originals`) + SQLite metadata
  catalog mirrored into vector payloads; originals read-only. (CE_PLAN §6.7, §7)
- **D-18 — Anti-DRM: metadata-filter-before-similarity + Summary-Augmented Chunking (SAC).** Prevents
  "right clause, wrong client" retrieval. (CE_PLAN §9, §10)
- **D-19 — Mechanical span-level citation verification in code.** A cited span must mechanically
  overlap an actually-retrieved chunk's offsets, or the claim is rejected before display. The prompt
  alone is not trusted. (CE_PLAN §10)
- **D-20 — Production deployment: Docker Compose** (Qdrant + FastAPI/LlamaIndex + thin UI), Ollama on
  host. Qdrant drops out if LanceDB is chosen. (CE_PLAN §6.8, §13)

## Hardware

- **D-21 — Pilot runs on the in-hand MacBook Pro 14" M4 Pro, 24GB unified.** No production hardware
  purchase until SC-1..SC-7 pass and the attorney has seen the demo. (CE_PLAN §12)
- **D-22 — Production target (recommended): Mac Studio M4 Max, 64–128GB unified** (Option A
  appliance); CUDA path (RTX 5070 Ti/5080/5090) only if latency/scale demands it. Do not buy on spec.
  (CE_PLAN §12)

## Resolved project questions (CE_PLAN §16)

- **D-23 — Single solo attorney, single-tenant v1.** Multi-user is a later concern.
- **D-24 — PDF first (born-digital and scanned), then DOCX, then TXT.** Scanned PDFs are first-class.
- **D-25 — No remote access in v1** (local/air-gapped); Tailscale only revisited later with written
  approval.
- **D-26 — First production corpus: a few thousand documents** (drives the 14B–32B / 16–32GB sweet
  spot; 70B unnecessary).
- **D-27 — Support model: ongoing managed** (Jake owns updates/backups/model refreshes on a defined
  cadence). Exact cadence + response SLA still to pin down with the attorney.

## Still open / to confirm

- **O-1 — `bge-m3` vs `qwen3-embedding`** final choice pending evaluation against the legal golden
  set. (CE_PLAN §6.5) — relevant from Milestone 2 onward.
- **O-2 — Support cadence + response-time SLA** numbers, to confirm with the attorney. (CE_PLAN §16
  Q10)
