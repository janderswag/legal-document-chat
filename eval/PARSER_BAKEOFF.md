# Parser bake-off — PyMuPDF vs Docling (citation fidelity)

**Milestone 2-3.** Prompted by a community review: *"your citations are only as good as the
positions the parser hands back… contracts are full of nested tables, multi-column clauses,
and the odd scanned exhibit."* This is the right concern for a citation-grade pipeline, so we
benchmarked the parse layer directly.

Harness: [`eval/parser_bakeoff.py`](parser_bakeoff.py). Input: the deterministic synthetic
fee-schedule exhibit from [`pipeline/build_table_corpus.py`](../pipeline/build_table_corpus.py)
(page 1 prose, page 2 a ruled table). All synthetic — no real data. Both parsers already
installed; **no new dependencies added.**

## Result

| parser | cell_recall | row_reading_order | column_structure | absent_rejection | page_attribution | fully_local | composite |
|---|---|---|---|---|---|---|---|
| **docling** (`do_ocr=False`) | 1.0 | 1.0 | ✅ | ✅ | ✅ | ✅¹ | **1.0** |
| pymupdf (current pipeline) | 1.0 | 1.0 | ❌ | ✅ | ✅ | ✅ | 0.8 |

On this clean ruled grid **both parsers tie on every span-citation metric**: every ground-truth
cell is recovered as a contiguous substring, on the correct page, in row reading order, with the
fabricated value rejected and page attribution intact. The **only** discriminator is
**column structure**: Docling reconstructs the table as a grid, so `$132,300` can be cited as
*the 2026 Annual License Fee*; the current PyMuPDF path flattens the table to a line list, so
column membership must be inferred positionally.

## The important caveat — Docling is NOT local out of the box ¹

With default settings Docling's OCR engine (RapidOCR) **downloaded ~30 MB of model weights from
`modelscope.cn` on first run, ignoring `HF_HUB_OFFLINE=1`** — a network egress event that
violates hard-safety-rule #3. It only stays fully local with **`do_ocr=False`** (correct for
born-digital contracts anyway) or by pre-provisioning models offline. This must be locked down
before Docling goes anywhere near the ingestion path.

## Recommendation

- Docling wins **only where table/column structure matters** for the answer; for pure page+span
  location on born-digital text the current PyMuPDF path is already sound, faster, and
  unconditionally local.
- If we adopt Docling, do it **table-scoped with `do_ocr=False`**, and treat model provisioning
  as an explicit, audited, offline step — never a silent first-run download.

## Limitations / next steps

- **Runs on one document.** The full golden set (`eval/golden_manifest.jsonl`, 63 span facts
  across 6 docs) is **not reproducible here** — `documents/` is git-ignored and the source PDFs
  are absent. The same six metrics extend over all 63 facts once those PDFs are restored.
- **Scanned/OCR arm not benchmarked.** The reviewer's "scanned exhibit" case needs the OCR path
  (RapidOCR/Tesseract) — deliberately deferred because it's the heavy, network-sensitive arm.
- **"liteparse" not evaluated** — unverified tool name; excluded until confirmed local.
- A third option worth a look: PyMuPDF's own `page.find_tables()` (structure without Docling's
  model footprint), which the current pipeline does not use.
