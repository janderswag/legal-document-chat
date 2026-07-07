"""P1.3 — first-run sample matter: a brand-new user reaches a cited answer with ZERO setup.

On a truly fresh install (no matters in the catalog at all), seed one clearly-synthetic
"Sample Matter (Demo)" with three small generated PDFs and ingest them through the NORMAL
KB path (kb_ingest -> .lancedb_kb), so New Chat can answer a suggested question against
real page+span citations immediately. Everything is generated locally with PyMuPDF at
seed time (no binary fixtures in git, hard rule #1: synthetic only, each page banner-
labelled SYNTHETIC). Seeding never runs when any matter exists — it can't touch, mix
with, or shadow user data (D-35 matter isolation is untouched; this is ordinary KB data).

Seeding needs the local Ollama embedder, which on a fresh machine isn't up until the
setup wizard finishes — so maybe_seed_async() waits (bounded) for readiness in a daemon
thread and then seeds. Loopback Ollama only; no document data leaves the machine.
"""

import threading
import time
from pathlib import Path

import fitz

import catalog
import kb_ingest
from routes_kb import KB_DB, KB_DOCS

SAMPLE_MATTER_NAME = "Sample Matter (Demo)"
SAMPLE_MATTER_SLUG = catalog.slugify(SAMPLE_MATTER_NAME)   # "sample-matter-demo"

# Shown as one-click chips on the Chat empty state (P1.4). Each is answerable with a
# page+span citation from the seeded documents below.
SUGGESTED_QUESTIONS = [
    "What is the monthly fee under the services agreement?",
    "How much notice is required to terminate the agreement for convenience?",
    "What retainer deposit does the engagement letter require?",
]

# Document copy stays em-dash-free: the base-14 Helvetica PDF font cannot encode U+2014
# (it renders as "?"), and the owner's copy rules disallow em-dashes anyway.
_BANNER = "SYNTHETIC SAMPLE DOCUMENT - NOT A REAL AGREEMENT. Generated for demo use only."

_DOCS = {
    "sample-services-agreement.pdf": (
        "MASTER SERVICES AGREEMENT\n\n"
        "This Master Services Agreement (the \"Agreement\") is entered into between "
        "Northwind Logistics LLC, a Delaware limited liability company (\"Client\"), and "
        "Meridian Consulting Group, Inc. (\"Provider\").\n\n"
        "1. SERVICES. Provider will supply supply-chain advisory services as described in "
        "each executed Statement of Work.\n\n"
        "2. FEES. Client will pay Provider a monthly fee of $12,500, invoiced on the first "
        "business day of each month. Invoices are payable net thirty (30) days.\n\n"
        "3. TERM. The initial term of this Agreement is twenty-four (24) months from the "
        "Effective Date, renewing for successive twelve (12) month periods unless either "
        "party gives written notice of non-renewal at least ninety (90) days before the "
        "end of the then-current term.\n\n"
        "4. TERMINATION FOR CONVENIENCE. Either party may terminate this Agreement for "
        "convenience upon sixty (60) days prior written notice to the other party.\n\n"
        "5. LIMITATION OF LIABILITY. Each party's aggregate liability under this Agreement "
        "is capped at the total fees paid by Client in the twelve (12) months preceding "
        "the event giving rise to the claim.\n\n"
        "6. GOVERNING LAW. This Agreement is governed by the laws of the State of "
        "Delaware, without regard to its conflict-of-laws rules."
    ),
    "sample-engagement-letter.pdf": (
        "ENGAGEMENT LETTER\n\n"
        "Re: Engagement of Calloway & Finch LLP by Northwind Logistics LLC\n\n"
        "Dear Ms. Alvarez,\n\n"
        "Thank you for selecting Calloway & Finch LLP to represent Northwind Logistics "
        "LLC in connection with the Meridian Consulting Group contract review.\n\n"
        "Our fees for this engagement will be billed at $425 per hour for partners and "
        "$250 per hour for associates. We require an initial retainer deposit of $7,500, "
        "which will be held in trust and applied against our final invoice.\n\n"
        "We will invoice monthly, and invoices are due within thirty (30) days of "
        "receipt. Out-of-pocket expenses (filing fees, courier, travel) are billed at "
        "cost with no markup.\n\n"
        "Either party may end the engagement at any time on written notice, subject to "
        "applicable rules of professional conduct.\n\n"
        "Sincerely,\nDaniel Finch, Partner"
    ),
    "sample-meeting-notes.pdf": (
        "MEETING NOTES: NORTHWIND / MERIDIAN RENEWAL DISCUSSION\n\n"
        "Attendees: R. Alvarez (Northwind GC), D. Finch (Calloway & Finch), T. Osei "
        "(Meridian account lead).\n\n"
        "1. Renewal timeline. The current services agreement renews automatically unless "
        "notice of non-renewal is given ninety (90) days before term end. The team set an "
        "internal deadline of October 15, 2026 to decide on renewal.\n\n"
        "2. Indemnification. Northwind raised that the current agreement contains no "
        "indemnification clause for third-party claims. Meridian agreed to consider "
        "adding one in the renewal draft.\n\n"
        "3. Fee discussion. Meridian proposed increasing the monthly fee from $12,500 to "
        "$13,750 at renewal. Northwind will counter after reviewing usage data.\n\n"
        "4. Action items. Finch to circulate a redline adding an indemnification clause; "
        "Alvarez to confirm the renewal decision date with the operations team."
    ),
}

_seed_lock = threading.Lock()
_seed_started = False


def _write_pdf(dest, body):
    """US-letter pages of born-digital text, paginated by paragraph (idempotent
    overwrite). insert_textbox returns >=0 iff everything fit; on overflow the trial
    page is deleted and retried with fewer paragraphs."""
    paras = body.split("\n\n")
    with fitz.open() as doc:
        i = 0
        while i < len(paras):
            placed = False
            for n in range(len(paras) - i, 0, -1):
                page = doc.new_page(width=612, height=792)
                page.insert_textbox(fitz.Rect(72, 40, 540, 58), _BANNER,
                                    fontsize=7, fontname="helv")
                spill = page.insert_textbox(fitz.Rect(72, 72, 540, 730),
                                            "\n\n".join(paras[i:i + n]),
                                            fontsize=11, fontname="helv")
                if spill >= 0:
                    i += n
                    placed = True
                    break
                doc.delete_page(-1)
            if not placed:          # a single paragraph too tall for a page — impossible
                raise ValueError(f"sample paragraph does not fit a page: {dest.name}")
        doc.save(str(dest))


def seed_sample_matter(db_path=None, kb_db=None, kb_docs=None):
    """Create + ingest the sample matter on a FRESH catalog only. Returns the matter
    slug when seeded, else None (any existing matter means a non-fresh install)."""
    if catalog.list_matters(db_path=db_path):
        return None
    matter = catalog.create_matter(SAMPLE_MATTER_NAME, db_path=db_path)
    slug = matter["slug"]
    dest_dir = Path(kb_docs or KB_DOCS) / slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    for filename, body in _DOCS.items():
        dest = dest_dir / filename
        _write_pdf(dest, body)
        doc = catalog.add_document(slug, dest, filename=filename, status="parsing",
                                   db_path=db_path)
        kb_ingest.ingest_document(doc["id"], str(dest), slug,
                                  str(kb_db or KB_DB), db_path)
    return slug


def _wait_and_seed(max_wait_s):
    """Poll local readiness (Ollama + pinned models), then seed. Bounded, best-effort:
    on a machine that never becomes ready the thread just exits — the guided empty
    state (P1.4) still walks the user through creating a matter manually."""
    from routes_setup import setup_status
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        if catalog.list_matters():
            return None          # user (or a prior run) got there first — never touch
        try:
            if setup_status()["ready"]:
                return seed_sample_matter()
        except Exception:
            pass
        time.sleep(3.0)
    return None


def maybe_seed_async(max_wait_s=1800):
    """Fire the seed thread once per process, and only when the catalog is empty."""
    global _seed_started
    with _seed_lock:
        if _seed_started:
            return False
        if catalog.list_matters():
            return False
        _seed_started = True
    threading.Thread(target=_wait_and_seed, args=(max_wait_s,),
                     name="sample-matter-seed", daemon=True).start()
    return True
