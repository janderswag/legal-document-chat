"""Task 1 — per-type text extraction, normalized to one page-record shape.

Dispatches on file suffix:
  .pdf        -> ingestion per-page routing (born-digital text layer vs OCR for scans)
  .docx       -> python-docx paragraphs (single page_number=1; DOCX has no fixed pages)
  .txt / .md  -> read_text (single page_number=1)
  .eml        -> stdlib email parse: headers + best text body (UX-6 email import)
  .html/.htm  -> script/style-stripped visible text (UX-11)
  .vtt / .srt -> subtitle/transcript cues as "[HH:MM:SS] text" lines (UX-11 — the
                 format Zoom/Teams/Meet hand out for meeting transcripts)
  .csv        -> rows joined per line (UX-11)
  .json       -> pretty-printed text (UX-11)
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


def _one_page(path, text, source):
    return [{
        "source_filename": Path(path).name,
        "page_number": 1,
        "page_text": text,
        "source": source,
        "ocr_failed": False,
    }]


def _html(path):
    """Visible text from an HTML file: script/style blocks dropped, tags stripped,
    entities decoded. Stdlib only."""
    import html as _h
    import re as _re
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    raw = _re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
    raw = _re.sub(r"(?i)<br\s*/?>|</p>|</div>|</h[1-6]>|</li>|</tr>", "\n", raw)
    raw = _re.sub(r"<[^>]+>", " ", raw)
    text = _h.unescape(raw)
    text = "\n".join(_re.sub(r"[ \t]+", " ", ln).strip()
                     for ln in text.splitlines())
    return _one_page(path, _re.sub(r"\n{3,}", "\n\n", text).strip(), "html")


def _subtitles(path):
    """WebVTT/SRT meeting transcripts (UX-11): cue text with a searchable
    "[HH:MM:SS]" start-time prefix per cue, speaker tags kept. This is the export
    format of Zoom, Teams, and Meet transcripts."""
    import re as _re
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    out, stamp = [], None
    timing = _re.compile(
        r"(\d{1,2}:)?(\d{1,2}):(\d{2})[.,]\d{3}\s*-->\s*")
    for ln in lines:
        t = ln.strip()
        if not t or t.upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        m = timing.match(t)
        if m:
            h = (m.group(1) or "0:").rstrip(":")
            stamp = f"[{int(h):02d}:{int(m.group(2)):02d}:{m.group(3)}]"
            continue
        if t.isdigit():                     # SRT cue counter
            continue
        t = _re.sub(r"<v(?:\.[^ >]*)?\s+([^>]+)>", r"\1: ", t)  # <v Speaker> -> Speaker:
        t = _re.sub(r"</?[cibu][^>]*>|</v>", "", t)             # residual format tags
        out.append(f"{stamp} {t}" if stamp else t)
        stamp = None
    return _one_page(path, "\n".join(out), Path(path).suffix.lstrip(".").lower())


def _csv(path):
    import csv as _csv
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        rows = [" | ".join(cell.strip() for cell in row)
                for row in _csv.reader(f)]
    return _one_page(path, "\n".join(rows), "csv")


def _json(path):
    import json as _json
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    try:
        text = _json.dumps(_json.loads(raw), indent=2, ensure_ascii=False)
    except ValueError:
        text = raw                          # malformed JSON ingests as plain text
    return _one_page(path, text, "json")


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
    if suffix in (".html", ".htm"):
        return _html(path)
    if suffix in (".vtt", ".srt"):
        return _subtitles(path)
    if suffix == ".csv":
        return _csv(path)
    if suffix == ".json":
        return _json(path)
    raise ValueError(f"unsupported document type: {suffix!r} ({path.name})")
