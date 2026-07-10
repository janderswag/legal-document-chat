"""Self-heal a poisoned encryption state at startup (v0.3.2).

If the Keychain master key changes out from under the encrypted catalog — a
Migration Assistant restore, an OS reinstall, Keychain corruption, or the D-81
incident — the production catalog becomes permanently undecryptable. Before
this guard, the app crashed on startup with a MISLEADING "port 8000" error, and
because the data dir survives an app reinstall, delete-and-redownload did not
fix it. The user was bricked with no path forward.

This runs as the FIRST startup step. If the catalog cannot be opened with the
current master key, it moves the WHOLE encrypted data set ASIDE (never deletes)
so the app starts fresh instead of bricking. The ciphertext is preserved on
disk in case a key is ever recovered from a backup.

Conservative by construction — a transient failure must never nuke good data:
  - only the real encrypted PRODUCTION catalog is considered,
  - it acts only when the master key is OBTAINABLE (keyvault refuses to
    fabricate a key on a failed read, so reaching the "won't open" branch means
    we hold a real key that simply does not fit — a persistent mismatch, not a
    transient lock),
  - it acts only when the catalog file is non-empty AND encrypted-format AND
    genuinely fails to open,
  - it renames aside with a timestamp; it never deletes.
"""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import apppaths
import catalog


def _catalog_opens(db_path, key_hex):
    """True if the catalog decrypts + reads with this key; False on a decrypt/
    corruption error. Any other error is re-raised (we only self-heal on a
    clear can't-decrypt signal)."""
    from sqlcipher3 import dbapi2 as sqlcipher
    conn = sqlcipher.connect(str(db_path))
    try:
        conn.execute(f"PRAGMA key = \"x'{key_hex}'\"")
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return True
    except sqlcipher.DatabaseError:
        # "file is not a database" — wrong key / corrupt header
        return False
    finally:
        conn.close()


def _detach_volume(mount_point):
    """Best-effort unmount of a mounted sparsebundle before we move its dir."""
    subprocess.run(["hdiutil", "detach", str(mount_point), "-force"],
                   capture_output=True)


def recover_if_unreadable(now=None, detach=_detach_volume):
    """If the production catalog is undecryptable with the current master key,
    move the data dir aside and return the aside Path. Otherwise return None.
    Safe to call unconditionally at startup."""
    if sys.platform != "darwin":
        return None
    data_root = apppaths.data_root()
    db_path = catalog._PRODUCTION_DB
    # nothing to recover: no catalog, empty, or plain (unencrypted) sqlite
    if not db_path.exists() or db_path.stat().st_size == 0:
        return None
    if not catalog.is_encrypted(db_path):
        return None
    # a failed key READ raises here (keyvault refuses to fabricate); if we can't
    # even get a key we must NOT touch data — the catalog may be fine.
    try:
        key_hex = catalog._master_key().hex()
    except Exception:
        return None
    try:
        if _catalog_opens(db_path, key_hex):
            return None                      # healthy — leave everything alone
    except Exception:
        return None                          # unexpected error: don't risk data

    # Confirmed: encrypted catalog that will not open with the real key.
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    aside = data_root.with_name(data_root.name + f".unreadable-{stamp}")
    # detach any mounted KB volume under the data dir first (can't move a mount)
    import routes_kb
    kb_mount = routes_kb.KB_DB
    if Path(kb_mount).is_mount():
        detach(kb_mount)
    data_root.rename(aside)
    return aside
