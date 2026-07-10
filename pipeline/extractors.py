"""Task 1 — per-type text extraction, normalized to one page-record shape.

Dispatches on file suffix:
  .pdf        -> ingestion per-page routing (born-digital text layer vs OCR for scans)
  .docx       -> python-docx paragraphs (single page_number=1; DOCX has no fixed pages)
  .txt / .md  -> read_text (single page_number=1)
  .eml        -> stdlib email parse: headers + best text body (UX-6 email import)
  anything else -> ValueError (the orchestrator quarantines it, fail-loud, §8)

Every record is normalized to:
  {source_filename, page_number, page_text, source, ocr_failed}
so the orchestrator and downstream chunking see one shape regardless of format. PDFs
preserve real page numbers; DOCX/TXT/MD are best-effort single-page (§8 step 5) — we do
NOT fake page splits.
"""

from pathlib import Path

from ingestion import extract_pages_ocr

_TEXT_SUFFIXES = {".txt", ".md"}


def _pdf(path):
    """Per-page route: born-digital pages use PyMuPDF text, image-only pages OCR.
    extract_pages_ocr already tags source ('pymupdf'|'tesseract') and ocr_failed."""
    out = []
    for r in extract_pages_ocr(path):
        out.append({
            "source_filename": r["source_filename"],
            "page_number": r["page_number"],
            "page_text": r["page_text"],
            "source": r["source"],
            "ocr_failed": r["ocr_failed"],
        })
    return out


def _docx(path):
    from docx import Document
    doc = Document(str(path))
    text = "\n".join(p.text for p in doc.paragraphs)
    return [{
        "source_filename": Path(path).name,
        "page_number": 1,  # DOCX has no fixed page model (§8 step 5)
        "page_text": text,
        "source": "docx",
        "ocr_failed": False,
    }]


def _text(path):
    return [{
        "source_filename": Path(path).name,
        "page_number": 1,
        "page_text": Path(path).read_text(encoding="utf-8"),
        "source": Path(path).suffix.lstrip(".").lower(),  # "txt" | "md"
        "ocr_failed": False,
    }]


def _eml(path):
    """RFC-822 email (.eml), UX-6 email import: headers + best text body as a single
    page. Stdlib email only (no new deps, no network). text/plain preferred;
    text/html fallback is tag-stripped. Attachments are NOT extracted here — their
    filenames are listed in the text so they stay searchable, and the user can drop
    the attachment file itself into the matter."""
    import email
    import email.policy
    import html as _html
    import re as _re

    msg = email.message_from_bytes(Path(path).read_bytes(), policy=email.policy.default)
    lines = []
    for h in ("From", "To", "Cc", "Date", "Subject"):
        v = msg.get(h)
        if v:
            lines.append(f"{h}: {v}")

    body = ""
    part = msg.get_body(preferencelist=("plain",))
    if part is not None:
        body = part.get_content()
    else:
        part = msg.get_body(preferencelist=("html",))
        if part is not None:
            body = _re.sub(r"<[^>]+>", " ", part.get_content())
            body = _html.unescape(_re.sub(r"\s+", " ", body)).strip()

    attachments = [p.get_filename() for p in msg.iter_attachments() if p.get_filename()]
    text = "\n".join(lines)
    if body:
        text += "\n\n" + body
    if attachments:
        text += "\n\n[Attachments: " + ", ".join(attachments) + "]"
    return [{
        "source_filename": Path(path).name,
        "page_number": 1,   # an email has no page model — single page, like .txt
        "page_text": text,
        "source": "eml",
        "ocr_failed": False,
    }]


def extract(path):
    """Extract normalized page records from a supported document. Raises ValueError on
    an unsupported suffix (so the orchestrator quarantines it)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf(path)
    if suffix == ".docx":
        return _docx(path)
    if suffix in _TEXT_SUFFIXES:
        return _text(path)
    if suffix == ".eml":
        return _eml(path)
    raise ValueError(f"unsupported document type: {suffix!r} ({path.name})")
