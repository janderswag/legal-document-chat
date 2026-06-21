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
