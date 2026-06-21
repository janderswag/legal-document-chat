"""Task 3 — build the FULL searchable store (.lancedb_full) including OCR'd pages.

Chunks the corpus PDFs (born-digital + image-only scans) with per-page OCR routing
(chunking.chunk_corpus(ocr=True)) and embeds them via bge-m3 (loopback Ollama) into
pipeline/.lancedb_full — a SEPARATE store from the live pipeline/.lancedb that backs
M2-8 (D-40). The live store is NEVER touched here.

Also materializes a scan-ONLY fixture (no born-digital twin, unique matter) so the
end-to-end SC-2 proof has an OCR'd page as its sole possible answer source.

Local-only: file IO + PyMuPDF render + local Tesseract OCR + loopback bge-m3 embedding.
"""

import json
import tempfile
from pathlib import Path

import fitz

from build_scanned_corpus import rasterize_to_image_pdf
from chunking import chunk_corpus
from embed_store import build_store

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
CORPUS = REPO_ROOT / "documents" / "synthetic_corpus" / "corpus"
CORPUS_MANIFEST = REPO_ROOT / "eval" / "corpus_manifest.jsonl"
FULL_CHUNKS = REPO_ROOT / "documents" / "synthetic_corpus" / "chunks_full"
FULL_DB = PIPELINE_DIR / ".lancedb_full"

VELEZ_FILE = "scan_only_velez_settlement.pdf"
VELEZ_MATTER = "Velez Settlement (Scan Only)"


def _ensure_velez_scan():
    """A scan-ONLY synthetic doc (image-only, no born-digital twin) with a unique matter
    and a unique fact — so an OCR'd page is the SOLE source for the SC-2 e2e proof. Idempotent."""
    out = CORPUS / VELEZ_FILE
    CORPUS.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "velez.pdf"
            with fitz.open() as doc:
                page = doc.new_page(width=612, height=792)
                page.insert_textbox(
                    fitz.Rect(72, 72, 540, 720),
                    "SYNTHETIC — NOT REAL\n\n"
                    "SETTLEMENT MEMORANDUM — Velez Matter\n\n"
                    "The total settlement amount payable to the claimant is $88,250, "
                    "due within thirty (30) days of execution of this memorandum.",
                    fontsize=13, fontname="helv",
                )
                doc.save(src)
            rasterize_to_image_pdf(src, out, dpi=300)

    entries = [json.loads(l) for l in CORPUS_MANIFEST.read_text().splitlines() if l.strip()]
    if not any(e["filename"] == VELEZ_FILE for e in entries):
        entries.append({"filename": VELEZ_FILE, "format": "scanned_pdf",
                        "document_type": "correspondence", "matter_or_client": VELEZ_MATTER,
                        "synthetic": True})
        CORPUS_MANIFEST.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")


def build():
    """Chunk (OCR-aware) the corpus PDFs and (over)write .lancedb_full. Returns the chunks."""
    _ensure_velez_scan()
    FULL_CHUNKS.mkdir(parents=True, exist_ok=True)
    chunks = chunk_corpus(CORPUS, CORPUS_MANIFEST, out_dir=FULL_CHUNKS, ocr=True)
    build_store(FULL_CHUNKS / "chunks.jsonl", db_path=str(FULL_DB))
    return chunks


if __name__ == "__main__":
    chunks = build()
    pdfs = sorted({c["source_filename"] for c in chunks})
    ocr_pages = {(c["source_filename"], c["page_number"]) for c in chunks if c.get("source") == "tesseract"}
    print(f"built {FULL_DB} from {len(pdfs)} PDFs, {len(chunks)} chunks "
          f"({len(ocr_pages)} OCR'd pages)")
