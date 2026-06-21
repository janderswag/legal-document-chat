"""D1 — author a SYNTHETIC court-style form fixture exercising the bankruptcy-parser
techniques reimplemented on PyMuPDF: a horizontal rule line with entered data above it,
pre-printed labels vs entered-data in distinct fonts/sizes. Synthetic — NOT REAL.

PyMuPDF only (no new dep). Body is git-ignored (D-28); the builder + known values are
tracked so tests rebuild deterministically.
"""

from pathlib import Path

import fitz

PIPELINE_DIR = Path(__file__).resolve().parent
FORMS_DIR = PIPELINE_DIR.parent / "documents" / "synthetic_corpus" / "forms"
FORM_PDF = FORMS_DIR / "synthetic_court_form.pdf"

BANNER = "SYNTHETIC - NOT REAL - fabricated court form for local development."
# Pre-printed labels (Helvetica, 11pt) vs entered data (Courier, 9pt) above rule lines.
LABEL_FONT, LABEL_SIZE = "helv", 11
INPUT_FONT, INPUT_SIZE = "cour", 9
ENTERED = {"debtor": "JANE Q PUBLIC", "case_no": "24-12345-ABC"}


def build_court_form(out_path=FORM_PDF):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 60), "UNITED STATES BANKRUPTCY COURT (SYNTHETIC)",
                     fontsize=12, fontname="hebo")
    page.insert_text((72, 78), BANNER, fontsize=8, fontname=LABEL_FONT)

    # Field 1: label, entered data above a rule line.
    page.insert_text((72, 130), "Debtor Name:", fontsize=LABEL_SIZE, fontname=LABEL_FONT)
    page.insert_text((170, 145), ENTERED["debtor"], fontsize=INPUT_SIZE, fontname=INPUT_FONT)
    page.draw_line((168, 150), (430, 150), color=(0, 0, 0), width=0.7)  # rule line

    # Field 2: label, entered data above a second rule line.
    page.insert_text((72, 185), "Case Number:", fontsize=LABEL_SIZE, fontname=LABEL_FONT)
    page.insert_text((170, 200), ENTERED["case_no"], fontsize=INPUT_SIZE, fontname=INPUT_FONT)
    page.draw_line((168, 205), (430, 205), color=(0, 0, 0), width=0.7)

    doc.save(str(out_path))
    doc.close()
    return out_path


if __name__ == "__main__":
    p = build_court_form()
    print(f"built synthetic court form -> {p} ({p.stat().st_size} bytes)")
