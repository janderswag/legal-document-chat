"""Move 1a (D-69) — build the SCALE eval store (.lancedb_scale) + stratified questions.

Purpose: the 50-chunk golden store cannot see recall at scale (top-5 there is 10% of the
whole store, and the D-66 search audit measured identifier-class queries already failing
dense-only). This builds a scratch store where top-5 is ~0.05% of the pool:

  - the ORIGINAL golden corpus documents, re-chunked through the PRODUCTION KB chunker
    (kb_ingest._chunk_pages — the exact pipeline /chat retrieves against), and
  - ~1,200 deterministic synthetic filler documents (seed 42) across ~40 filler matters,
    ~40 of which carry PLANTED facts targeted by new questions stratified by query class
    {identifier, statute-cite, party-name, defined-term, paraphrase, cross-doc}, plus
    hard-negative TWIN pairs (original + amendment in the SAME matter, different values).

Writes: pipeline/.lancedb_scale (git-ignored scratch — NEVER .lancedb or .lancedb_kb)
and eval/scale_questions.jsonl (tracked: question, class, matter, gold filename+page).
Loopback bge-m3 embedding only; synthetic content only (hard rule #1).
"""

import json
import random
from pathlib import Path

from embed_store import add_chunks
from kb_ingest import _chunk_pages

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
CORPUS = REPO_ROOT / "documents" / "synthetic_corpus" / "corpus"
CORPUS_MANIFEST = REPO_ROOT / "eval" / "corpus_manifest.jsonl"
SCALE_DB = PIPELINE_DIR / ".lancedb_scale"
QUESTIONS_OUT = REPO_ROOT / "eval" / "scale_questions.jsonl"

SEED = 42
N_GENERIC_FILLER = 1200

_FIRST = ["Marisol", "Dmitri", "Priya", "Colton", "Anneke", "Rafael", "Ingrid", "Tobias",
          "Yusuf", "Beatrix", "Callum", "Odette", "Hector", "Sigrid", "Percival", "Lucinda"]
_LAST = ["Vantrease", "Okafor", "Lindqvist", "Barbosa", "Whitlock", "Nakagawa", "Fenwick",
         "Oyelaran", "Castellanos", "Drummond", "Vereen", "Szabo", "Marchetti", "Holloway"]
_CO = ["Meridian", "Northgate", "Bluewater", "Ironwood", "Cascade", "Pinnacle", "Harborview",
       "Stonebridge", "Lakeshore", "Redwood", "Summit", "Crestline", "Fairhaven", "Oakmont"]
_CO2 = ["Logistics", "Consulting", "Holdings", "Manufacturing", "Analytics", "Partners",
        "Ventures", "Industries", "Services", "Group"]

_BANNER = "SYNTHETIC - NOT REAL - FOR EVAL USE ONLY"


def _company(rng):
    return f"{rng.choice(_CO)} {rng.choice(_CO2)} LLC"


def _person(rng):
    return f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"


def _generic_doc(rng, i):
    """A 2-page generic filler contract with plausible-but-untargeted content."""
    a, b = _company(rng), _company(rng)
    fee = rng.randrange(2, 90) * 250
    days = rng.choice([30, 45, 60, 90])
    p1 = (f"{_BANNER}\n\nSERVICES AGREEMENT\n\nThis Services Agreement is entered into "
          f"between {a} (\"Client\") and {b} (\"Provider\").\n\n1. SERVICES. Provider will "
          f"perform the professional services described in each statement of work.\n\n"
          f"2. FEES. Client shall pay Provider a monthly service fee of ${fee:,}, invoiced "
          f"monthly and payable net {days} days.\n\n3. TERM. The initial term is "
          f"{rng.choice([12, 24, 36])} months from the Effective Date.\n\n"
          + " ".join(f"Section {s}. Standard provision text regarding administration, "
                     f"cooperation, and recordkeeping obligations of the parties."
                     for s in range(4, 4 + rng.randrange(3, 6))))
    p2 = (f"4. TERMINATION. Either party may terminate for convenience on "
          f"{rng.choice([30, 60, 90])} days written notice.\n\n5. LIABILITY. Aggregate "
          f"liability is capped at fees paid in the preceding twelve months.\n\n"
          f"6. GOVERNING LAW. This Agreement is governed by the laws of the State of "
          f"{rng.choice(['Delaware', 'New York', 'Ohio', 'Illinois', 'Colorado'])}.\n\n"
          + " ".join(f"Section {s}. Additional standard provision text concerning notices, "
                     f"assignment, severability, and entire agreement."
                     for s in range(7, 7 + rng.randrange(2, 5))))
    return f"filler_{i:04d}_services_agreement.txt", [p1, p2]


def _planted_docs(rng):
    """Docs carrying PLANTED facts + the stratified questions that target them.

    Returns (docs, questions): docs = [(filename, matter, [page_texts])];
    questions = [{qid, class, question, matter, gold_filename, gold_page}]."""
    docs, questions = [], []

    def plant(qid, qclass, matter, filename, pages, question, gold_page):
        docs.append((filename, matter, pages))
        questions.append({"qid": qid, "class": qclass, "question": question,
                          "matter": matter, "gold_filename": filename,
                          "gold_page": gold_page})

    def distract(matter, stem, bodies):
        """Same-GENRE distractor docs inside the gold doc's matter — the realistic hard
        case: the right memo among eight similar memos, not among unrelated boilerplate.
        Without these, the matter pre-filter would make in-matter recall trivially
        perfect for every config and the eval would measure nothing."""
        for j, b in enumerate(bodies):
            docs.append((f"{stem}_distractor{j}.txt", matter, [b]))

    # --- identifier class (bare numbers, invoice/case/bar numbers, amounts) ---------
    idents = [
        ("SQ-ID-01", "INV-77341", "$14,862.50",
         "What is the total amount of invoice INV-77341?"),
        ("SQ-ID-02", "Case No. 5:26-cv-04417", "$150,000",
         "What amount in controversy is stated in case number 5:26-cv-04417?"),
        ("SQ-ID-03", "bar number 662104", "Vivian Ashcombe-Reyes",
         "Which attorney holds bar number 662104?"),
        ("SQ-ID-04", "purchase order PO-90218", "$8,340",
         "What is the value of purchase order PO-90218?"),
        ("SQ-ID-05", "check number 004471", "$23,750",
         "What amount was paid by check number 004471?"),
        ("SQ-ID-06", "claim number CLM-2026-8817", "$61,200",
         "What is the claimed amount under claim number CLM-2026-8817?"),
        ("SQ-ID-07", "docket entry 47", "motion to compel",
         "What was filed at docket entry 47?"),
        ("SQ-ID-08", "tax parcel 118-22-407", "$412,000",
         "What is the assessed value of tax parcel 118-22-407?"),
    ]
    for n, (qid, ident, value, q) in enumerate(idents):
        matter = f"scale-planted-{n:02d}"
        body = (f"{_BANNER}\n\nACCOUNTING MEMORANDUM\n\nRe: reconciliation for the matter "
                f"file.\n\nThe record reflects that {ident} corresponds to {value}. "
                f"Supporting documentation is attached to the ledger.\n\n"
                + "General narrative about routine reconciliation procedures. " * 8)
        plant(qid, "identifier", matter, f"planted_{qid.lower()}.txt", [body], q, 1)
        distract(matter, f"planted_{qid.lower()}", [
            (f"{_BANNER}\n\nACCOUNTING MEMORANDUM\n\nRe: reconciliation for the matter "
             f"file.\n\nThe record reflects that INV-{rng.randrange(10000, 99999)} "
             f"corresponds to ${rng.randrange(80, 900) * 25:,}.{50 + j} adjusted per the "
             f"ledger notes. Check number {rng.randrange(1000, 9999):06d} and claim "
             f"CLM-2026-{rng.randrange(1000, 9999)} were reviewed in the same cycle.\n\n"
             + "General narrative about routine reconciliation procedures. " * 8)
            for j in range(8)])

    # --- statute-cite class ----------------------------------------------------------
    statutes = [
        ("SQ-ST-01", "Ohio Rev. Code 1345.02", "consumer sales practices",
         "Which Ohio statute section is cited on consumer sales practices?"),
        ("SQ-ST-02", "15 U.S.C. 1692g", "debt validation notice",
         "Which federal statute is cited for the debt validation notice requirement?"),
        ("SQ-ST-03", "Cal. Civ. Code 1942.4", "untenantable dwelling rent",
         "Which California statute is cited about collecting rent on an untenantable dwelling?"),
        ("SQ-ST-04", "Del. Code tit. 6, 18-305", "member inspection rights",
         "Which Delaware statute is cited for LLC member inspection rights?"),
        ("SQ-ST-05", "N.Y. Gen. Bus. Law 349", "deceptive acts and practices",
         "Which New York statute is cited regarding deceptive acts and practices?"),
    ]
    other_cites = ["Tex. Bus. & Com. Code 17.46", "Fla. Stat. 501.204", "12 U.S.C. 2605",
                   "Mich. Comp. Laws 445.903", "Wash. Rev. Code 19.86.020",
                   "Colo. Rev. Stat. 6-1-105", "N.J. Stat. 56:8-2", "815 ILCS 505/2"]
    for n, (qid, cite, topic, q) in enumerate(statutes):
        matter = f"scale-planted-{8 + n:02d}"
        body = (f"{_BANNER}\n\nMEMORANDUM OF LAW (SYNTHETIC)\n\nThe governing provision on "
                f"{topic} is {cite}, which the tribunal has applied in comparable disputes. "
                f"Counsel should address the elements in the next filing.\n\n"
                + "Discussion of general procedural posture and scheduling. " * 8)
        plant(qid, "statute-cite", matter, f"planted_{qid.lower()}.txt", [body], q, 1)
        distract(matter, f"planted_{qid.lower()}", [
            (f"{_BANNER}\n\nMEMORANDUM OF LAW (SYNTHETIC)\n\nThe governing provision on "
             f"{rng.choice(['unfair competition', 'servicing disputes', 'trade practices', 'escrow handling'])} "
             f"is {oc}, applied in several comparable disputes before this tribunal.\n\n"
             + "Discussion of general procedural posture and scheduling. " * 8)
            for oc in other_cites])

    # --- party-name class (rare proper nouns) ---------------------------------------
    parties = [
        ("SQ-PN-01", "Thaddeus Okonkwo-Beaumont", "the project engineer of record",
         "What role does Thaddeus Okonkwo-Beaumont hold?"),
        ("SQ-PN-02", "Wilhelmina Szczepanska", "the assigned claims adjuster",
         "Who is Wilhelmina Szczepanska in this matter?"),
        ("SQ-PN-03", "Barnaby Featherstonhaugh", "the subcontractor's site foreman",
         "What is Barnaby Featherstonhaugh's role?"),
        ("SQ-PN-04", "Xiomara Quispe-Larrain", "the certified interpreter at the hearing",
         "What was Xiomara Quispe-Larrain's role at the hearing?"),
        ("SQ-PN-05", "Ozymandias Vlachopoulos", "the receiver appointed by the court",
         "Who was appointed receiver?"),
        ("SQ-PN-06", "Perpetua Nightingale-Ross", "the escrow agent",
         "Who serves as the escrow agent?"),
        ("SQ-PN-07", "Evander Kalogeropoulos", "the testifying damages expert",
         "Who is the testifying damages expert?"),
    ]
    other_roles = ["opposing counsel of record", "the court reporter", "the mediator",
                   "the process server", "the notary public", "the records custodian",
                   "the paralegal on the file", "the billing coordinator"]
    for n, (qid, name, role, q) in enumerate(parties):
        matter = f"scale-planted-{13 + n:02d}"
        body = (f"{_BANNER}\n\nCASE CONTACTS MEMO\n\nFor the file: {name} is {role} in this "
                f"matter. Contact details are maintained separately in the secure directory.\n\n"
                + "Additional narrative on scheduling and correspondence logistics. " * 8)
        plant(qid, "party-name", matter, f"planted_{qid.lower()}.txt", [body], q, 1)
        distract(matter, f"planted_{qid.lower()}", [
            (f"{_BANNER}\n\nCASE CONTACTS MEMO\n\nFor the file: {_person(rng)} is "
             f"{r} in this matter. Contact details are maintained separately.\n\n"
             + "Additional narrative on scheduling and correspondence logistics. " * 8)
            for r in other_roles])

    # --- defined-term class ----------------------------------------------------------
    terms = [
        ("SQ-DT-01", "Restricted Data", "any dataset delivered under Exhibit C, including "
         "derived aggregates", "How is the term Restricted Data defined?"),
        ("SQ-DT-02", "Qualified Overrun", "documented cost growth above four percent of the "
         "baseline budget", "What is a Qualified Overrun under the agreement?"),
        ("SQ-DT-03", "Designated Facility", "the fabrication plant at 42 Kestrel Way, Toledo",
         "What location is the Designated Facility?"),
        ("SQ-DT-04", "Holdback Amount", "ten percent of each progress payment",
         "What is the Holdback Amount?"),
        ("SQ-DT-05", "Cure Window", "fifteen business days after written notice of default",
         "How long is the Cure Window?"),
        ("SQ-DT-06", "Key Personnel", "the individuals listed on Schedule 2 whose replacement "
         "requires Client consent", "Who counts as Key Personnel?"),
    ]
    other_terms = [("Baseline Budget", "the approved budget attached as Exhibit A"),
                   ("Progress Payment", "a monthly payment against certified work in place"),
                   ("Service Credit", "a two percent fee reduction for missed SLA targets"),
                   ("Renewal Notice", "written notice given ninety days before term end"),
                   ("Change Order", "a signed writing modifying scope, price, or schedule"),
                   ("Punch List", "the closeout list of incomplete or defective items"),
                   ("Retainage", "amounts withheld pending final acceptance"),
                   ("Substantial Completion", "the stage when the work is usable for its purpose")]
    for n, (qid, term, definition, q) in enumerate(terms):
        matter = f"scale-planted-{20 + n:02d}"
        body = (f"{_BANNER}\n\nDEFINITIONS RIDER\n\n\"{term}\" means {definition}. "
                f"Capitalized terms not defined here have the meanings in the base agreement.\n\n"
                + "Boilerplate recitals and construction rules for the rider. " * 8)
        plant(qid, "defined-term", matter, f"planted_{qid.lower()}.txt", [body], q, 1)
        distract(matter, f"planted_{qid.lower()}", [
            (f"{_BANNER}\n\nDEFINITIONS RIDER\n\n\"{t}\" means {d}. Capitalized terms not "
             f"defined here have the meanings in the base agreement.\n\n"
             + "Boilerplate recitals and construction rules for the rider. " * 8)
            for t, d in other_terms])

    # --- paraphrase class (formal fact, colloquial question) -------------------------
    paras = [
        ("SQ-PA-01", "In the event Lessee fails to remit rent within five days of the due "
         "date, Lessor may assess a late charge of $175 and pursue possession.",
         "What happens if the tenant stops paying rent on time?"),
        ("SQ-PA-02", "Employee shall refrain from soliciting Company clients for a period of "
         "eighteen months following separation.",
         "How long after leaving is the employee barred from poaching clients?"),
        ("SQ-PA-03", "Carrier's liability for cargo loss is limited to $2.50 per pound unless "
         "a higher value is declared in writing.",
         "How much can you get back if the shipper loses your freight?"),
        ("SQ-PA-04", "Either party may suspend performance where an event beyond reasonable "
         "control persists for more than thirty days.",
         "Can they pause the deal if something out of their hands drags on?"),
        ("SQ-PA-05", "Warranty claims must be presented within one year of substantial "
         "completion of the work.",
         "How long do you have to complain about defective work?"),
        ("SQ-PA-06", "The undersigned guarantor unconditionally guarantees payment of all "
         "sums due under the note.",
         "Who is on the hook if the borrower does not pay?"),
        ("SQ-PA-07", "Overtime shall be compensated at one and one half times the regular "
         "hourly rate for hours exceeding forty per week.",
         "What do workers get paid for extra hours?"),
        ("SQ-PA-08", "Settlement proceeds shall be disbursed within ten days of receipt of "
         "the executed release.",
         "How fast does the money go out once the release is signed?"),
    ]
    other_clauses = [
        "Deliverables are deemed accepted unless rejected in writing within ten days.",
        "All notices must be sent by certified mail to the addresses on the signature page.",
        "This agreement may be executed in counterparts, each deemed an original.",
        "Neither party may assign this agreement without prior written consent.",
        "Headings are for convenience only and do not affect interpretation.",
        "The prevailing party in any action is entitled to reasonable attorneys fees.",
        "Any amendment must be in a writing signed by both parties.",
        "The waiver of one breach is not a waiver of any later breach.",
    ]
    for n, (qid, fact, q) in enumerate(paras):
        matter = f"scale-planted-{26 + n:02d}"
        body = (f"{_BANNER}\n\nAGREEMENT EXCERPT\n\n{fact}\n\n"
                + "Surrounding standard clauses on notices and interpretation. " * 8)
        plant(qid, "paraphrase", matter, f"planted_{qid.lower()}.txt", [body], q, 1)
        distract(matter, f"planted_{qid.lower()}", [
            (f"{_BANNER}\n\nAGREEMENT EXCERPT\n\n{c}\n\n"
             + "Surrounding standard clauses on notices and interpretation. " * 8)
            for c in other_clauses])

    # --- cross-doc class (matter has 3 docs; the fact lives in exactly one) ----------
    for n in range(6):
        qid = f"SQ-XD-{n + 1:02d}"
        matter = f"scale-planted-{34 + n:02d}"
        rate = 300 + 25 * n
        decoy1 = (f"{_BANNER}\n\nCOVER LETTER\n\nEnclosed are the engagement materials for "
                  f"your review and signature.\n\n" + "Transmittal boilerplate. " * 10)
        decoy2 = (f"{_BANNER}\n\nCONFLICT CHECK MEMO\n\nNo conflicts were identified for "
                  f"this engagement.\n\n" + "Conflict procedure narrative. " * 10)
        gold = (f"{_BANNER}\n\nENGAGEMENT TERMS\n\nProfessional fees will be billed at "
                f"${rate} per hour for principal time on this engagement.\n\n"
                + "Standard billing and expense-reimbursement terms. " * 10)
        docs.append((f"planted_{qid.lower()}_cover.txt", matter, [decoy1]))
        docs.append((f"planted_{qid.lower()}_conflict.txt", matter, [decoy2]))
        docs.append((f"planted_{qid.lower()}_terms.txt", matter, [gold]))
        distract(matter, f"planted_{qid.lower()}", [
            (f"{_BANNER}\n\nENGAGEMENT CORRESPONDENCE\n\nFollow-up regarding scheduling "
             f"and document collection for the engagement; associate time is discussed "
             f"in the staffing plan, not here.\n\n" + "Engagement admin narrative. " * 9)
            for _ in range(6)])
        questions.append({"qid": qid, "class": "cross-doc",
                          "question": "What hourly rate applies to principal time?",
                          "matter": matter,
                          "gold_filename": f"planted_{qid.lower()}_terms.txt",
                          "gold_page": 1})

    # --- hard-negative TWINS (same matter: original + amendment, different values) ---
    for n in range(10):
        qid = f"SQ-HN-{n + 1:02d}"
        matter = f"scale-twins-{n:02d}"
        old_fee, new_fee = 5000 + 500 * n, 6250 + 500 * n
        original = (f"{_BANNER}\n\nMASTER AGREEMENT (ORIGINAL)\n\n2. FEES. Client shall pay "
                    f"a monthly fee of ${old_fee:,} during the initial term.\n\n"
                    + "Original standard terms text. " * 10)
        amendment = (f"{_BANNER}\n\nFIRST AMENDMENT TO MASTER AGREEMENT\n\nSection 2 is "
                     f"amended so that the monthly fee is ${new_fee:,} effective January 1, "
                     f"2026, superseding the original fee.\n\n"
                     + "Amendment boilerplate and ratification text. " * 10)
        docs.append((f"twin_{qid.lower()}_original.txt", matter, [original]))
        docs.append((f"twin_{qid.lower()}_amendment.txt", matter, [amendment]))
        distract(matter, f"twin_{qid.lower()}", [
            (f"{_BANNER}\n\n{['SECOND', 'THIRD', 'FOURTH'][j % 3]} AMENDMENT TO MASTER "
             f"AGREEMENT\n\nSection {4 + j} is amended to revise the "
             f"{rng.choice(['notice address', 'insurance minimums', 'reporting cadence', 'key personnel list'])}. "
             f"All other terms remain in effect; fees are unchanged by this amendment.\n\n"
             + "Amendment boilerplate and ratification text. " * 9)
            for j in range(6)])
        questions.append({"qid": qid, "class": "hard-negative",
                          "question": "What is the current monthly fee under the amendment?",
                          "matter": matter,
                          "gold_filename": f"twin_{qid.lower()}_amendment.txt",
                          "gold_page": 1})
    return docs, questions


def _golden_docs():
    """Filename -> matter for the golden corpus. The GOLDEN manifest is authoritative
    (it matches the live eval store — e.g. the Renfrew demand letter is scoped to the
    Pemberton matter it concerns, NOT the corpus manifest's per-file label; using the
    corpus label made 8 golden questions structurally unanswerable here). Corpus
    manifest fills in files that carry no golden facts."""
    matter_of = {}
    for line in CORPUS_MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            matter_of[r["filename"]] = r["matter_or_client"]
    golden = REPO_ROOT / "eval" / "golden_manifest.jsonl"
    for line in golden.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if not r["expected_absent_topics"]:
                matter_of[r["filename"]] = r["matter_or_client"]
    return matter_of


def build():
    if SCALE_DB.exists():
        raise SystemExit(f"refusing to overwrite existing scale store: {SCALE_DB} "
                         "(delete it explicitly to rebuild)")
    from extractors import extract

    rng = random.Random(SEED)
    all_chunks = []

    # 1) golden corpus through the PRODUCTION chunker
    matter_of = _golden_docs()
    golden_files = sorted(CORPUS.iterdir())
    n_golden = 0
    for f in golden_files:
        if f.suffix.lower() not in (".pdf", ".docx", ".txt", ".md"):
            continue
        matter = matter_of.get(f.name)
        if matter is None:
            continue
        pages = extract(f)
        all_chunks.extend(_chunk_pages(pages, matter, f.name))
        n_golden += 1
    print(f"golden: {n_golden} docs -> {len(all_chunks)} chunks", flush=True)

    # 2) planted + twins
    docs, questions = _planted_docs(rng)
    for filename, matter, pages in docs:
        page_dicts = [{"page_text": t, "page_number": i + 1, "source": "txt"}
                      for i, t in enumerate(pages)]
        all_chunks.extend(_chunk_pages(page_dicts, matter, filename))

    # 3) generic filler — assigned INTO the planted/twin matters (cycling) so every
    # eval matter is realistically LARGE (~25 generic + ~9 same-genre docs each). A
    # planted fact alone in a tiny matter would make in-matter recall@5 trivially
    # perfect under the pre-filter and the eval would measure nothing.
    eval_matters = sorted({q["matter"] for q in questions})
    for i in range(N_GENERIC_FILLER):
        filename, pages = _generic_doc(rng, i)
        matter = eval_matters[i % len(eval_matters)]
        page_dicts = [{"page_text": t, "page_number": j + 1, "source": "txt"}
                      for j, t in enumerate(pages)]
        all_chunks.extend(_chunk_pages(page_dicts, matter, f"generic_{i:04d}_{filename}"))
    print(f"total chunks to embed: {len(all_chunks)} across "
          f"{len(eval_matters)} large eval matters + golden matters", flush=True)

    # embed + write in batches (whole-store build; loopback bge-m3)
    B = 256
    for s in range(0, len(all_chunks), B):
        add_chunks(all_chunks[s:s + B], SCALE_DB)
        print(f"  embedded {min(s + B, len(all_chunks))}/{len(all_chunks)}", flush=True)

    QUESTIONS_OUT.write_text(
        "".join(json.dumps(q) + "\n" for q in questions), encoding="utf-8")
    print(f"wrote {len(questions)} stratified questions -> {QUESTIONS_OUT}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    build()
