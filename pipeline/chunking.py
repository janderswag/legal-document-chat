"""M2-2 — Docling structure normalization + page/section-aware chunking with SAC.

Builds on the M2-1 substrate (``ingestion.extract_pages``): page numbers and char
offsets are taken from M2-1's authoritative per-page text (the offset source of
truth for the later M2-6 span check). Docling supplies the section-detection
signal only — it is run with OCR disabled (born-digital corpus) and its detected
section headers are reconciled against the reliable ``#``/``##`` heading markers
present in the M2-1 page text (which also carry the heading level and exact
offsets). char offsets on each chunk are relative to that chunk's PAGE text.

SAC (D-18): a short, deterministic context line (matter + document type + section
breadcrumb) is prepended to each chunk's embedding text so identical boilerplate
clauses across different matters carry distinguishing context. No LLM is used.

Scope (M2-2): structure + chunking only. No embedding, vector DB, reranker, LLM,
retrieval, or HTTP surface.
"""

import json
import os
import re
from pathlib import Path

from ingestion import extract_pages, extract_pages_ocr

# Below this many non-whitespace extractable chars a PDF page has no real text layer
# (image-only) -> it is treated as scanned for the OCR-aware corpus path (T3/T4).
_SCANNED_TEXT_CHARS = 20

# A heading line in the M2-1 page text, e.g. "## ARTICLE 9 — INDEMNIFICATION".
_HEADING_RE = re.compile(r"(?m)^(#{1,6})[ \t]+(\S.*?)\s*$")
_DASHES = str.maketrans({"—": "-", "–": "-", "−": "-"})


def _normalize_heading(text):
    """Whitespace- and dash-normalized form for comparing headings to Docling."""
    return re.sub(r"\s+", " ", text.translate(_DASHES)).strip().lower()


def load_doc_metadata(manifest_path):
    """filename -> {matter, document_type}, sourced from the manifest (never invented)."""
    meta = {}
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("filename") and rec["filename"] not in meta:
                meta[rec["filename"]] = {
                    "matter": rec.get("matter_or_client"),
                    "document_type": rec.get("document_type"),
                }
    return meta


def docling_section_headers(pdf_path, cache_dir):
    """Section-header / title strings Docling detects in the PDF (OCR disabled).

    Cached per filename under ``cache_dir`` (document-derived text -> git-ignored)
    so re-chunking needs no Docling run and makes no network egress.
    """
    pdf_path = Path(pdf_path)
    cache_file = Path(cache_dir) / ".docling_headers.json"
    cache = {}
    if cache_file.exists():
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
    if pdf_path.name in cache:
        return cache[pdf_path.name]

    # Loopback-only default (project safety rule #4): serve Docling's layout
    # models from the local HF cache and suppress the hub revision-check, so a
    # conversion makes ZERO egress. A fresh machine performs the approved one-time
    # model fetch by setting DOCLING_ALLOW_MODEL_FETCH=1 for that run only.
    if os.environ.get("DOCLING_ALLOW_MODEL_FETCH") != "1":
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    # Lazy import so a warm cache never loads Docling/torch (keeps re-chunk fast +
    # egress-free). Docling fetches its layout models on first run only.
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions(do_ocr=False)
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )
    doc = converter.convert(pdf_path).document
    headers = []
    for item, _level in doc.iterate_items():
        label = str(getattr(item, "label", "")).lower()
        text = (getattr(item, "text", "") or "").strip()
        if text and ("section_header" in label or label.endswith("title")):
            headers.append(text)

    cache[pdf_path.name] = headers
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return headers


def chunk_pdf(pdf_path, doc_meta, docling_headers, ocr=False):
    """Page/section-aware chunks for one PDF.

    Each chunk: {source_filename, matter, document_type, page_number, section,
    char_start, char_end, text, embedding_text, section_detected_by_docling}.
    char_start/char_end index the chunk's PAGE text (M2-1 substrate).

    ``ocr=False`` (default, unchanged): born-digital text via ``extract_pages``.
    ``ocr=True`` (T3/T4): per-page routing via ``extract_pages_ocr`` — image-only pages
    are OCR'd; each chunk additionally carries ``source`` ("pymupdf"|"tesseract")
    provenance, and pages whose OCR failed (low confidence) are SKIPPED (not indexed as
    authoritative garbage, §8). OCR'd pages carry no ``#`` heading markers, so their
    section breadcrumb is empty — expected (offsets/text/verification still hold).
    """
    pdf_path = Path(pdf_path)
    meta = doc_meta.get(pdf_path.name, {})
    matter = meta.get("matter")
    doc_type = meta.get("document_type")
    docling_norm = {_normalize_heading(h) for h in docling_headers}

    def confirmed_by_docling(heading_text):
        nh = _normalize_heading(heading_text)
        return any(nh == d or nh in d or d in nh for d in docling_norm)

    chunks = []
    stack = []  # list of (level, heading_text); persists across pages
    stack_confirmed = False
    pages = extract_pages_ocr(pdf_path) if ocr else extract_pages(pdf_path)
    for page in pages:
        if ocr and page.get("ocr_failed"):
            continue  # low-confidence OCR -> not authoritative, don't index (§8)
        pt = page["page_text"]
        pno = page["page_number"]
        headings = [(m.start(), len(m.group(1)), m.group(2)) for m in _HEADING_RE.finditer(pt)]
        boundaries = sorted({0, *(h[0] for h in headings)})
        head_at = {h[0]: h for h in headings}
        for idx, start in enumerate(boundaries):
            end = boundaries[idx + 1] if idx + 1 < len(boundaries) else len(pt)
            text = pt[start:end]
            if not text.strip():
                continue
            if start in head_at:
                _, level, htext = head_at[start]
                stack = [x for x in stack if x[0] < level]
                stack.append((level, htext))
                stack_confirmed = confirmed_by_docling(htext)
            section = " › ".join(t for _, t in stack)
            sac = f"[Matter: {matter} | Type: {doc_type} | Section: {section}]\n{text}"
            chunk = {
                "source_filename": pdf_path.name,
                "matter": matter,
                "document_type": doc_type,
                "page_number": pno,
                "section": section,
                "char_start": start,
                "char_end": end,
                "text": text,
                "embedding_text": sac,
                "section_detected_by_docling": bool(stack) and stack_confirmed,
            }
            if ocr:  # provenance only on the OCR-aware path (keeps born-digital keys exact)
                chunk["source"] = page.get("source", "tesseract")
            chunks.append(chunk)
    return chunks


def chunk_corpus(pdf_dir, manifest_path, out_dir=None, ocr=False):
    """Chunk all PDFs in ``pdf_dir``; write chunks.jsonl to a git-ignored dir.

    Returns the list of all chunks. Output (document text) is written under
    ``<pdf_dir>/../chunks/`` which is git-ignored (D-28).

    ``ocr=True`` (T3) routes each page (born-digital text vs OCR for image-only) and
    carries OCR provenance. Image-only PDFs carry no text-layer headings, so Docling
    section detection is skipped for them; for born-digital PDFs Docling is still used
    but its failure is non-fatal (section degrades to empty rather than crashing a build).
    """
    pdf_dir = Path(pdf_dir)
    out_dir = Path(out_dir) if out_dir else pdf_dir.parent / "chunks"
    out_dir.mkdir(parents=True, exist_ok=True)
    doc_meta = load_doc_metadata(manifest_path)

    all_chunks = []
    for pdf in sorted(pdf_dir.glob("*.pdf")):
        if ocr:
            is_scanned = all(
                len(p["page_text"].strip()) < _SCANNED_TEXT_CHARS for p in extract_pages(pdf)
            )
            if is_scanned:
                headers = []
            else:
                try:
                    headers = docling_section_headers(pdf, out_dir)
                except Exception:
                    headers = []  # section degrades, build continues
        else:
            headers = docling_section_headers(pdf, out_dir)
        all_chunks.extend(chunk_pdf(pdf, doc_meta, headers, ocr=ocr))

    with open(out_dir / "chunks.jsonl", "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return all_chunks
