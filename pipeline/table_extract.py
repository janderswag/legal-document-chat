"""T-TBL — Docling TableFormer table EXTRACTION (D-50/D-51).

Turn on Docling's table-structure model (`do_table_structure=True`) — already shipped in
our installed Docling — and pull each table to a Markdown grid carrying its page number
and bbox provenance. This is the EXTRACTION layer only: ``extract_tables(pdf)`` returns
per-table ``{source_filename, page_number, bbox, markdown}``. Chunking / embedding /
answering are downstream (table_ingest).

Offset-routing (D-51): this is the heavy Docling path, run ONLY on table-bearing docs.
The born-digital PROSE path (PyMuPDF, ingestion/chunking) is UNCHANGED — table chunks are
a separate, Docling-sourced chunk type whose offsets index their own Markdown (never mixed
with PyMuPDF page offsets on one chunk).

Air-gap (rule #4): by default the Docling models are served from the local HF cache with
the hub revision-check suppressed, so a conversion makes ZERO network egress. A fresh
machine performs the owner-approved one-time fetch by setting ``DOCLING_ALLOW_MODEL_FETCH=1``
for that run; afterwards it runs fully offline.

Model pin (D-11 style): the TableFormer weights live in ``docling-project/docling-models``,
pinned to ``TABLEFORMER_REVISION`` below — a revision change forces a table re-index.
"""

import os
from pathlib import Path

# Air-gap (rule #4): force HF/Transformers offline at IMPORT time — before any
# huggingface_hub import, including a bare standalone ``assert_model_revision()`` (the A0
# startup enforcement) — so even that makes ZERO egress. The owner-approved one-time fetch
# opts out per-run by launching with ``DOCLING_ALLOW_MODEL_FETCH=1`` set before import.
if os.environ.get("DOCLING_ALLOW_MODEL_FETCH") != "1":
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# docling-project/docling-models @ v2.3.0 (the snapshot cached on this machine; contains
# the TableFormer weights). Pinned D-11 style — a change forces table re-index.
TABLEFORMER_REVISION = "fc0f2d45e2218ea24bce5045f58a389aed16dc23"

_MODEL_REPO_DIR = "models--docling-project--docling-models"


def cached_model_revision():
    """The commit hash the local HF cache resolves for docling-project/docling-models, or
    ``None`` if it can't be determined unambiguously (e.g. a fresh machine before the
    approved one-time fetch). Reads the HF cache layout (refs/<tag> -> commit, else the
    single snapshot dir) — no network, no Docling import."""
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
        cache_root = Path(HF_HUB_CACHE)
    except Exception:
        cache_root = Path.home() / ".cache" / "huggingface" / "hub"
    repo = cache_root / _MODEL_REPO_DIR
    refs = repo / "refs"
    if refs.is_dir():
        commits = {p.read_text(encoding="utf-8").strip()
                   for p in refs.iterdir() if p.is_file()}
        commits.discard("")
        if len(commits) == 1:
            return commits.pop()
    snaps = repo / "snapshots"
    if snaps.is_dir():
        dirs = [p.name for p in snaps.iterdir() if p.is_dir()]
        if len(dirs) == 1:
            return dirs[0]
    return None


def assert_model_revision():
    """Fail loud if the cached Docling model snapshot differs from ``TABLEFORMER_REVISION``
    — a silent model swap must force a deliberate re-index, never silently change table
    extraction (D-50/D-53). Returns the resolved revision (or None when the cache can't be
    resolved — a fresh machine about to fetch; not blocked)."""
    rev = cached_model_revision()
    if rev is not None and rev != TABLEFORMER_REVISION:
        raise RuntimeError(
            f"TableFormer model revision mismatch: cached {rev!r} != pinned "
            f"{TABLEFORMER_REVISION!r}. A model change forces a table re-index — update "
            f"TABLEFORMER_REVISION deliberately (table_extract.py) after re-indexing.")
    return rev


def _bbox_dict(bbox):
    """JSON-serializable bbox from a Docling BoundingBox (page coordinates)."""
    return {
        "l": float(bbox.l), "t": float(bbox.t),
        "r": float(bbox.r), "b": float(bbox.b),
        "coord_origin": str(getattr(bbox, "coord_origin", "")),
    }


def extract_tables(pdf_path):
    """Extract every table in ``pdf_path`` to Markdown with page + bbox provenance.

    Returns a list of ``{source_filename, page_number, bbox, markdown}`` (one per table),
    in document order. An empty list means the doc has no detected tables (the caller
    skips the table path for it — latency, D-51). Loopback-only; never writes the file.
    """
    pdf_path = Path(pdf_path)

    # Offline by default (HF/Transformers offline env is set at IMPORT time above). On a
    # non-fetch run the cached snapshot must match the pin (a swap forces re-index); on a
    # fetch run the pin is what gets pulled, so the check is skipped there.
    if os.environ.get("DOCLING_ALLOW_MODEL_FETCH") != "1":
        assert_model_revision()

    # Lazy import so a caller that never extracts tables never loads Docling/torch.
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )
    doc = converter.convert(pdf_path).document

    tables = []
    for t in doc.tables:
        prov = t.prov[0] if t.prov else None
        tables.append({
            "source_filename": pdf_path.name,
            "page_number": int(prov.page_no) if prov else None,
            "bbox": _bbox_dict(prov.bbox) if prov else None,
            "markdown": t.export_to_markdown(doc).strip(),
        })
    return tables
