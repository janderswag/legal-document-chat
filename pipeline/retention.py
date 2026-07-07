"""Move 4 (D-72) — retention primitives: export-everything, disposition + honest
certificate. Legal holds + the hash-chained audit log live in catalog.py.

dispose_matter() is the ONLY code path that removes a whole matter, and it:
  1. REFUSES while a legal hold is active (FRCP 37(e) preservation; 409 upstream),
  2. removes chunks from the KB store and COMPACTS it (deleted rows leave the live
     files), line maps, chat threads, catalog rows, and managed copies (structurally
     locked to documents/kb/ — hard rule #5 unchanged: never an outside path),
  3. crypto-shreds the matter's DEK (D-73) and emits a Certificate of Disposition
     (NIST SP 800-88r2 App. C model) whose method is stated HONESTLY per artifact
     class: original documents earn "Purge (cryptographic erase)" only when every
     native was DEK-encrypted AND the key destruction actually happened; derived
     index data is always "Clear" (rows deleted + store compacted — inside the
     encrypted volume where one is mounted). One plain-era file in the tree keeps
     the originals at Clear. Never a blanket Purge claim.
Export ALWAYS happens before disposal in the API flow (Rule 1.16(d) surrender).
"""

import io
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import catalog
import keyvault

APP_VERSION = "0.2.0-dev"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _within(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False


def export_matter(matter_slug, kb_docs_root, db_path=None):
    """The matter's complete file as zip bytes: original natives + threads with
    citations + catalog manifest + this matter's audit slice. Read-only."""
    matter = catalog.get_matter(matter_slug, db_path=db_path)
    if matter is None:
        raise ValueError(f"unknown matter: {matter_slug!r}")
    docs = catalog.list_documents(matter_slug, db_path=db_path)
    threads = []
    for t in catalog.threads_for_matter(matter_slug, db_path=db_path):
        t["messages"] = catalog.messages_for_thread(t["id"], db_path=db_path)
        threads.append(t)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in docs:
            p = Path(d["stored_path"])
            if p.is_file() and _within(p, kb_docs_root):
                # D-73: surrender is PLAINTEXT — read_matter_file decrypts
                # DEK-encrypted natives (and passes plain ones through), so the
                # exported file matches the manifest checksum the attorney can verify.
                z.writestr(f"documents/{d['filename']}",
                           keyvault.read_matter_file(p, matter_slug, db_path=db_path))
        z.writestr("manifest/documents.json", json.dumps(docs, indent=2))
        z.writestr("manifest/matter.json", json.dumps(matter, indent=2))
        z.writestr("chats/threads.json", json.dumps(threads, indent=2))
        z.writestr("manifest/audit.json",
                   json.dumps(catalog.audit_entries(matter_slug, db_path=db_path), indent=2))
        z.writestr("README.txt",
                   "Complete matter file exported from docuchat.\n"
                   "documents/ holds the original files as uploaded (natives).\n"
                   "chats/threads.json holds every question, answer, and citation.\n"
                   "manifest/ holds checksums and the matter's audit trail.\n")
    catalog.audit_append("export", matter_slug,
                         f"{len(docs)} documents, {len(threads)} threads",
                         db_path=db_path)
    return buf.getvalue()


def dispose_matter(matter_slug, kb_db, kb_docs_root, db_path=None):
    """Disposition per the design doc §2. Returns the Certificate of Disposition dict.
    Callers MUST have offered export first (the route enforces the flow)."""
    matter = catalog.get_matter(matter_slug, db_path=db_path)
    if matter is None:
        raise ValueError(f"unknown matter: {matter_slug!r}")
    hold = catalog.active_hold(matter_slug, db_path=db_path)
    if hold:
        raise PermissionError(f"legal hold active since {hold['created']}: {hold['reason']}")

    docs = catalog.list_documents(matter_slug, db_path=db_path)
    doc_manifest = [{"filename": d["filename"], "sha256": d["checksum"],
                     "size_bytes": d["size_bytes"], "doc_type": d.get("doc_type", "document")}
                    for d in docs]

    # D-73: the Purge claim is earned per artifact class, never blanket. Originals
    # qualify only if EVERY native still on disk is DEK-encrypted (checked before
    # unlinking) AND the DEK destruction below actually happens; one plain-era file
    # in the tree keeps the originals at Clear — honestly.
    present = [Path(d["stored_path"]) for d in docs
               if Path(d["stored_path"]).is_file() and _within(d["stored_path"], kb_docs_root)]
    all_encrypted = bool(present) and all(keyvault.is_encrypted_file(p) for p in present)
    store_in_encrypted_volume = os.path.ismount(str(kb_db))

    # 1) vector store: delete the matter's chunks, then COMPACT so removed rows leave
    #    the live files (Lance keeps old versions until optimize/cleanup runs).
    store_state = "no-store"
    try:
        from embed_store import open_table
        table = open_table(str(kb_db))
        mt = matter_slug.replace("'", "''")
        table.delete(f"matter = '{mt}'")
        try:
            table.optimize(cleanup_older_than=__import__("datetime").timedelta(0))
        except TypeError:
            table.optimize()
        store_state = "deleted+compacted"
    except FileNotFoundError:
        pass
    except Exception as e:
        store_state = f"store-cleanup-incomplete: {type(e).__name__}"

    # 2) line maps, threads, catalog rows, managed copies (locked to documents/kb/)
    removed_files = 0
    for d in docs:
        catalog.delete_line_map(d["id"], db_path=db_path)
        p = Path(d["stored_path"])
        if p.is_file() and _within(p, kb_docs_root):
            p.unlink()
            removed_files += 1
        catalog.delete_document(d["id"], db_path=db_path)
    n_threads = catalog.delete_threads_for_matter(matter_slug, db_path=db_path)
    matter_dir = Path(kb_docs_root) / matter_slug
    if matter_dir.is_dir() and not any(matter_dir.iterdir()):
        matter_dir.rmdir()
    catalog.delete_matter(matter_slug, db_path=db_path)

    # D-73 crypto-shred: destroy the matter's wrapped DEK LAST (export needed it;
    # the files above are already unlinked). After this line the ciphertext of every
    # DEK-encrypted native — including copies in snapshots or backups — is
    # irrecoverable by anyone. Recorded as its own audit event when it happens.
    shredded = keyvault.destroy_matter_dek(matter_slug, db_path=db_path)
    if shredded:
        catalog.audit_append("crypto-shred", matter_slug,
                             "matter DEK destroyed (wrapped key NULLed)",
                             db_path=db_path)

    originals_purged = all_encrypted and shredded
    methods = {
        "original documents": (
            "Purge (cryptographic erase, NIST SP 800-88r2): every native was "
            "AES-256-GCM encrypted with a matter key that has been destroyed"
            if originals_purged else
            "Clear (files unlinked)"),
        "derived index data": (
            "Clear (rows deleted and store compacted, inside an encrypted volume)"
            if store_in_encrypted_volume else
            "Clear (rows deleted and store compacted)"),
    }
    caveats = ["OS snapshots and backups made before disposition are outside app control."]
    if originals_purged:
        caveats = [
            "Derived index data is Clear, not Purge: deleted and compacted inside "
            "the app's encrypted volume, whose volume key remains in use."
            if store_in_encrypted_volume else
            "Derived index data is Clear, not Purge: the vector store is not "
            "hosted on an encrypted volume on this install.",
            "Database copies made before disposition could retain the wrapped matter "
            "key; the app excludes its stores from Time Machine to prevent this.",
        ]
    else:
        caveats.append(
            "Purge (cryptographic erase) applies only when every original was "
            "encrypted with a destroyed matter key; that was not the case here.")

    chain_head = catalog.audit_append(
        "disposition", matter_slug,
        f"{len(docs)} documents, {n_threads} threads, store={store_state}, "
        f"crypto-shred={'yes' if shredded else 'no'}",
        db_path=db_path)

    return {
        "certificate": "Certificate of Disposition",
        "modeled_on": "NIST SP 800-88 Rev. 2, Appendix C",
        "matter": {"slug": matter_slug, "display_name": matter["display_name"]},
        "documents": doc_manifest,
        "threads_removed": n_threads,
        "method": (
            "Purge (cryptographic erase) for original documents; Clear for derived "
            "index data" if originals_purged else
            "Clear (files unlinked; vector store rows deleted and compacted)"),
        "methods": methods,
        "crypto_shred": shredded,
        "caveats": caveats,
        "store_state": store_state,
        "performed_at": _now(),
        "app_version": APP_VERSION,
        "audit_chain_head": chain_head,
    }
