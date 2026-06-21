"""Task 2 — assemble a 20-50 doc multi-format SYNTHETIC corpus for SC-1.

Reproducibly populates the git-ignored documents/synthetic_corpus/corpus/ with:
  - the 6 existing born-digital PDFs (copied),
  - 6 clean image-only "scanned" PDFs (rasterized; degraded variants are T4),
  - 4 DOCX + 5 TXT/MD fabricated documents (varied matters, all four document_types),
and writes the TRACKED type sidecar eval/corpus_manifest.jsonl (filename -> format,
document_type, matter, synthetic flag). All content is clearly SYNTHETIC — NOT REAL.

Local-only (file IO + PyMuPDF render). No network. Re-runnable (deterministic).
"""

from pathlib import Path

from docx import Document

from build_scanned_corpus import rasterize_to_image_pdf

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
PDF_DIR = REPO_ROOT / "documents" / "synthetic_corpus" / "pdf"
CORPUS = REPO_ROOT / "documents" / "synthetic_corpus" / "corpus"
SIDECAR = REPO_ROOT / "eval" / "corpus_manifest.jsonl"

_BANNER = "SYNTHETIC — NOT REAL — fabricated for local development (no real client data)."

# Existing born-digital PDFs -> document_type (matches eval/golden_manifest.jsonl).
_PDF_TYPES = {
    "nimbus_pemberton_msa.pdf": ("contract", "Pemberton Logistics (Nimbus MSA)"),
    "greenfield_castellano_lease.pdf": ("contract", "Castellano Studios (Greenfield Lease)"),
    "holloway_v_drakemoor_complaint.pdf": ("pleading", "Holloway v. Drakemoor Industries"),
    "tessaro_v_brightwater_order.pdf": ("pleading", "Tessaro v. Brightwater Mutual"),
    "public_domain_statutes.pdf": ("public_legal_text", "Public Domain (Reference)"),
    "renfrew_demand_letter.pdf": ("correspondence", "Renfrew Holdings (Demand)"),
}

# New DOCX docs: (filename, document_type, matter, [paragraphs]).
_DOCX = [
    ("arclight_consulting_agreement.docx", "contract", "Arclight Media (Consulting)", [
        "CONSULTING SERVICES AGREEMENT",
        _BANNER,
        "This Consulting Services Agreement is entered into between Arclight Media LLC "
        "(\"Client\") and Dunmore Advisory Group (\"Consultant\").",
        "1. Fees. Consultant shall be paid a monthly retainer of $12,750, due on the "
        "fifteenth day of each calendar month.",
        "2. Term. The initial term is eighteen (18) months and renews for successive "
        "twelve (12) month terms unless terminated on sixty (60) days written notice.",
        "3. Governing Law. This Agreement is governed by the laws of the State of Oregon.",
    ]),
    ("brightwater_vendor_nda.docx", "contract", "Tessaro v. Brightwater Mutual", [
        "MUTUAL NON-DISCLOSURE AGREEMENT",
        _BANNER,
        "This Mutual Non-Disclosure Agreement is made between Brightwater Mutual Insurance "
        "Co. and Calderon Vendor Services Inc.",
        "1. Confidential Information. Each party shall protect the other's Confidential "
        "Information for a period of five (5) years from the date of disclosure.",
        "2. Liquidated Damages. A breach of Section 1 carries liquidated damages of "
        "$25,000 per occurrence.",
    ]),
    ("voss_engagement_letter.docx", "correspondence", "Holloway v. Drakemoor Industries", [
        "ENGAGEMENT LETTER",
        _BANNER,
        "Dear Mr. Holloway: This letter confirms the engagement of Voss & Associates as "
        "counsel of record in Holloway v. Drakemoor Industries.",
        "Our hourly rate for this matter is $385 per hour, billed monthly. An initial "
        "retainer of $7,500 is required before work commences.",
        "Sincerely, Sabrina Voss, State Bar No. 388214.",
    ]),
    ("drakemoor_motion_to_compel.docx", "pleading", "Holloway v. Drakemoor Industries", [
        "MOTION TO COMPEL DISCOVERY",
        _BANNER,
        "Plaintiff Marcus Holloway respectfully moves this Court to compel Defendant "
        "Drakemoor Industries to produce documents responsive to Request No. 14.",
        "Defendant's responses were served forty-two (42) days after the deadline and "
        "remain deficient. Plaintiff seeks an order compelling production within ten (10) days.",
    ]),
]

# New TXT/MD docs: (filename, format, document_type, matter, body).
_TEXT = [
    ("castellano_intake_memo.txt", "txt", "correspondence", "Castellano Studios (Greenfield Lease)",
     _BANNER + "\n\nCLIENT INTAKE MEMO\nMatter: Castellano Studios commercial lease.\n"
     "Client reports the landlord, Greenfield Property Holdings LLC, has not returned the "
     "security deposit of $9,400 within the 30-day statutory window. Follow up on demand letter."),
    ("ucc_2_201_excerpt.md", "md", "public_legal_text", "Public Domain (Reference)",
     "# UCC § 2-201 — Statute of Frauds (excerpt)\n\n" + _BANNER + "\n\n"
     "A contract for the sale of goods for the price of $500 or more is not enforceable "
     "unless there is some writing sufficient to indicate that a contract for sale has been "
     "made and signed by the party against whom enforcement is sought."),
    ("pemberton_renewal_email.txt", "txt", "correspondence", "Pemberton Logistics (Nimbus MSA)",
     _BANNER + "\n\nFrom: ops@pemberton.example\nTo: counsel@firm.example\nSubject: Nimbus MSA renewal\n\n"
     "Please confirm whether the Nimbus master services agreement auto-renews. We believe "
     "the monthly service fee of $47,350 should remain fixed through the renewal term."),
    ("arclight_retainer_terms.md", "md", "contract", "Arclight Media (Consulting)",
     "# Retainer Terms — Arclight Media\n\n" + _BANNER + "\n\n"
     "- Monthly retainer: $12,750\n- Payment due: 15th of each month\n"
     "- Late fee: 1.5% per month on overdue balances\n- Governing law: State of Oregon"),
    ("drakemoor_deposition_summary.txt", "txt", "pleading", "Holloway v. Drakemoor Industries",
     _BANNER + "\n\nDEPOSITION SUMMARY — Witness: Elena Drakemoor\n"
     "The witness testified that the safety inspection on March 3 was not logged in the "
     "maintenance system. She acknowledged that Request No. 14 documents exist but were not produced."),
]


def _write_docx(path, paragraphs):
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    doc.save(str(path))


def build():
    CORPUS.mkdir(parents=True, exist_ok=True)
    sidecar = []

    # 1) born-digital PDFs (copied) + 2) clean scanned rasters
    for name, (dtype, matter) in _PDF_TYPES.items():
        src = PDF_DIR / name
        (CORPUS / name).write_bytes(src.read_bytes())
        sidecar.append({"filename": name, "format": "pdf",
                        "document_type": dtype, "matter_or_client": matter, "synthetic": True})
        scan_name = f"scan_{name}"
        rasterize_to_image_pdf(src, CORPUS / scan_name, dpi=300)
        sidecar.append({"filename": scan_name, "format": "scanned_pdf",
                        "document_type": dtype, "matter_or_client": matter, "synthetic": True})

    # 3) DOCX
    for name, dtype, matter, paras in _DOCX:
        _write_docx(CORPUS / name, paras)
        sidecar.append({"filename": name, "format": "docx",
                        "document_type": dtype, "matter_or_client": matter, "synthetic": True})

    # 4) TXT/MD
    for name, fmt, dtype, matter, body in _TEXT:
        (CORPUS / name).write_text(body, encoding="utf-8")
        sidecar.append({"filename": name, "format": fmt,
                        "document_type": dtype, "matter_or_client": matter, "synthetic": True})

    import json
    SIDECAR.write_text("".join(json.dumps(s) + "\n" for s in sidecar), encoding="utf-8")
    return sidecar


if __name__ == "__main__":
    side = build()
    import collections
    by_fmt = collections.Counter(s["format"] for s in side)
    by_type = collections.Counter(s["document_type"] for s in side)
    print(f"built {len(side)} docs -> {CORPUS}")
    print("formats:", dict(by_fmt))
    print("types:", dict(by_type))
    print("sidecar:", SIDECAR)
