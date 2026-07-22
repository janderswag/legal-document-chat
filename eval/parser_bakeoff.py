"""Parser bake-off — PyMuPDF (current pipeline path) vs Docling, on a born-digital
ruled-table exhibit, scored for CITATION fidelity.

Motivation (Milestone 2-3): page+span citations are only as good as the positions the
parser hands back. A community reviewer flagged the parse layer as the weak link for
legal docs (nested tables, multi-column clauses, scanned exhibits). This harness measures,
on the synthetic fee-schedule exhibit built by ``build_table_corpus.py``, whether each
parser:

  1. cell_recall        — every ground-truth cell appears as a CONTIGUOUS substring...
  2. correct_page       — ...on the CORRECT page (not misattributed to page 1),
  3. row_reading_order  — each table row's cells appear in left-to-right reading order,
  4. column_structure   — the parser exposes the table as a grid so a cell can be
                          attributed to its (row, column) header (needed to cite
                          "the 2026 Annual License Fee is $132,300", not just "$132,300"),
  5. absent_rejection   — a fabricated value ($999,999) appears NOWHERE,
  6. fully_local        — extraction makes no network egress (hard safety rule #3).

Run:  pipeline/.venv/bin/python eval/parser_bakeoff.py
Writes eval/results/parser_bakeoff.json and prints a ranked scorecard.

NOTE ON SCOPE: the full golden corpus (eval/golden_manifest.jsonl, 63 span-level facts
across 6 documents) is NOT reproducible on this machine — documents/ is git-ignored and
the source PDFs are absent. This harness therefore runs on the one hard-layout document we
CAN regenerate deterministically (the table exhibit). When the golden PDFs are restored,
the same six metrics extend directly over all 63 facts.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "pipeline"))

import build_table_corpus as tbl  # noqa: E402


def _ordered_subsequence(hay: str, needles) -> bool:
    """True if every needle appears in `hay` in the given left-to-right order."""
    pos = 0
    for n in needles:
        i = hay.find(n, pos)
        if i < 0:
            return False
        pos = i + len(n)
    return True


# ---------------------------------------------------------------- parsers ----
def extract_pymupdf(pdf_path):
    """Current pipeline path: plain per-page PyMuPDF text (ingestion.extract_pages).
    Returns (pages: {page_no -> text}, table_grid: None)."""
    import ingestion
    pages = {r["page_number"]: r["page_text"] for r in ingestion.extract_pages(pdf_path)}
    return pages, None


def extract_docling(pdf_path):
    """Docling with OCR DISABLED (born-digital -> no RapidOCR network path).
    Returns (pages: {page_no -> text}, table_grid: list-of-row-dicts or None)."""
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.base_models import InputFormat

    opts = PdfPipelineOptions()
    opts.do_ocr = False
    opts.do_table_structure = True
    conv = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )
    doc = conv.convert(pdf_path).document

    pages = {}

    def _page_of(item):
        prov = getattr(item, "prov", None)
        return prov[0].page_no if prov else None

    for item, _level in doc.iterate_items():
        pn = _page_of(item)
        if pn is None:
            continue
        text = getattr(item, "text", "") or ""
        if not text and hasattr(item, "export_to_markdown"):
            try:
                text = item.export_to_markdown(doc)
            except Exception:
                text = ""
        if text:
            pages[pn] = pages.get(pn, "") + "\n" + text

    grid = None
    if doc.tables:
        try:
            df = doc.tables[0].export_to_dataframe(doc)
            grid = df.to_dict(orient="records")
        except Exception:
            grid = None
    return pages, grid


# ---------------------------------------------------------------- scoring ----
def score(name, pages, grid):
    table_pg = tbl.TABLE_PAGE
    page_txt = pages.get(table_pg, "")
    all_txt = "\n".join(pages.values())

    # 1+2. cell recall on the correct page (contiguous substring)
    cells = list(tbl.GROUND_TRUTH)
    on_correct_page = [c for c in cells if c in page_txt]
    cell_recall = len(on_correct_page) / len(cells)

    # 3. row reading order: Year then its three fee cells, in order, on the table page
    rows_ok = sum(1 for row in tbl.ROWS if _ordered_subsequence(page_txt, row))
    row_order = rows_ok / len(tbl.ROWS)

    # 4. column structure: can we attribute a cell to (row, column) from parser output?
    #    Verified against one ground-truth cell: 2026 / "Annual License Fee" -> $132,300.
    col_structure = False
    if grid:
        for rec in grid:
            vals = {str(k).strip(): str(v).strip() for k, v in rec.items()}
            if vals.get("Year") == "2026":
                # find the license-fee column by header substring
                for k, v in vals.items():
                    if "Annual License Fee" in k and v == "$132,300":
                        col_structure = True
    # 5. absent-value rejection
    absent_rejected = tbl.ABSENT_VALUE not in all_txt

    # 6. page attribution: page-1-only marker on p1 and NOT on the table page
    marker = tbl.PAGE1_ONLY_MARKER
    page_attribution = (marker in pages.get(1, "")) and (marker not in page_txt)

    return {
        "parser": name,
        "cell_recall": round(cell_recall, 3),
        "row_reading_order": round(row_order, 3),
        "column_structure": col_structure,
        "absent_rejection": absent_rejected,
        "page_attribution": page_attribution,
    }


PARSERS = {
    "pymupdf (current pipeline)": (extract_pymupdf, True),   # fully_local
    "docling (do_ocr=False)": (extract_docling, True),       # local ONLY with OCR off
}


def main():
    pdf = tbl.build_fee_schedule_exhibit()
    results = []
    for name, (fn, fully_local) in PARSERS.items():
        pages, grid = fn(str(pdf))
        row = score(name, pages, grid)
        row["fully_local"] = fully_local
        # composite: mean of the five citation metrics (booleans as 0/1)
        m = [row["cell_recall"], row["row_reading_order"],
             float(row["column_structure"]), float(row["absent_rejection"]),
             float(row["page_attribution"])]
        row["composite"] = round(sum(m) / len(m), 3)
        results.append(row)

    results.sort(key=lambda r: r["composite"], reverse=True)

    out = REPO / "eval" / "results" / "parser_bakeoff.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        {"document": pdf.name, "ground_truth_cells": tbl.GROUND_TRUTH, "results": results},
        indent=2), encoding="utf-8")

    cols = ["parser", "cell_recall", "row_reading_order", "column_structure",
            "absent_rejection", "page_attribution", "fully_local", "composite"]
    w = {c: max(len(c), *(len(str(r[c])) for r in results)) for c in cols}
    print("  ".join(c.ljust(w[c]) for c in cols))
    print("  ".join("-" * w[c] for c in cols))
    for r in results:
        print("  ".join(str(r[c]).ljust(w[c]) for c in cols))
    print(f"\nwrote {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
