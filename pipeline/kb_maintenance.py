"""A0b — KB housekeeping: prune accumulated synthetic demo matters (D-53 carry-forward).

Removes a matter's chunks from the writable, git-ignored ``.lancedb_kb`` store, its rows
from the catalog, and its managed copies under ``documents/kb/<slug>/`` — and NOTHING else.
It never touches an eval baseline store, an original/synthetic-corpus document, or the
catalog of any matter not named. There is no UI delete route for matters (D-53); this is an
operator maintenance utility, run deliberately.
"""

import shutil
from pathlib import Path

import catalog
from embed_store import delete_doc

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
KB_DOCS = REPO_ROOT / "documents" / "kb"


def prune_matter(slug, kb_db, catalog_db=None, kb_docs=KB_DOCS):
    """Delete one matter's chunks (``kb_db``), catalog rows, and managed copies. Idempotent
    — pruning an absent matter is a no-op. Returns the number of documents removed."""
    docs = catalog.list_documents(slug, db_path=catalog_db)
    for d in docs:
        delete_doc(kb_db, d["filename"], slug)          # vector chunks (scoped)
        catalog.delete_document(d["id"], db_path=catalog_db)
    catalog.delete_matter(slug, db_path=catalog_db)
    managed = Path(kb_docs) / slug
    if managed.is_dir():
        shutil.rmtree(managed)                          # managed copies (documents/kb/ only)
    return len(docs)


def prune_matters(slugs, kb_db, catalog_db=None, kb_docs=KB_DOCS):
    """Prune several matters. Returns {slug: docs_removed}."""
    return {s: prune_matter(s, kb_db, catalog_db=catalog_db, kb_docs=kb_docs) for s in slugs}
