"""Encrypted KB volume (D-73, design §3): the LanceDB store lives inside an
AES-256 encrypted APFS sparse bundle, mounted AT the store path so every existing
query/ingest path is byte-identical — LanceDB just sees a directory.

The volume passphrase is a dedicated Keychain secret (keyvault.keychain_secret,
account ``kb-volume-key-v1``) — never a file, never in git, fed to hdiutil via
stdin so it never appears in argv. Mount happens once at app startup (the measured
~450ms is absorbed alongside the model preload, eval/ENCVOL_PROTO.md), eject at
shutdown. Non-macOS or no bundle present = plain-store posture, unchanged.

Migration to the volume is a separate rehearsed script
(``migrate_store_encvol.py``); this module only owns the volume lifecycle.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

import keyvault

log = logging.getLogger("docuchat.encvol")

import apppaths

KB_BUNDLE = apppaths.data_root() / ".lancedb_kb.sparsebundle"  # matches the .lancedb*/ gitignore
VOLUME_ACCOUNT = "kb-volume-key-v1"


def volume_passphrase():
    """The volume unlock secret (hex of a 32-byte Keychain secret)."""
    return keyvault.keychain_secret(VOLUME_ACCOUNT).hex()


def is_mounted(mountpoint):
    return os.path.ismount(str(mountpoint))


def create_volume(bundle, passphrase, volname="docuchat-kb", size="20g"):
    """Create an encrypted APFS sparse bundle (sparse: 'size' is a cap, not an
    allocation). Passphrase via stdin only."""
    r = subprocess.run(
        ["hdiutil", "create", "-type", "SPARSEBUNDLE", "-fs", "APFS",
         "-encryption", "AES-256", "-stdinpass", "-size", size,
         "-volname", volname, str(bundle)],
        input=passphrase, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"hdiutil create failed: {r.stderr.strip()}")


def mount(bundle, mountpoint, passphrase):
    """Attach the bundle at ``mountpoint`` (idempotent: already-mounted is a no-op)."""
    if is_mounted(mountpoint):
        return False
    Path(mountpoint).mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["hdiutil", "attach", str(bundle), "-stdinpass", "-nobrowse",
         "-mountpoint", str(mountpoint)],
        input=passphrase, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"hdiutil attach failed: {r.stderr.strip()}")
    return True


def eject(mountpoint):
    """Detach the volume; best-effort (a busy volume logs and stays)."""
    if not is_mounted(mountpoint):
        return False
    r = subprocess.run(["hdiutil", "detach", str(mountpoint)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        log.warning("could not eject %s: %s", mountpoint, r.stderr.strip())
        return False
    return True


def mount_kb_volume(kb_db, bundle=None, passphrase=None):
    """App-startup hook: mount the encrypted bundle at the KB store path. On a
    truly FRESH install (no bundle AND no store yet, macOS) the volume is created
    first, so new installs start encrypted instead of inheriting the plain-store
    posture. Returns a status string for Settings (no filesystem paths).
    ``passphrase`` is injectable for tests; production uses the Keychain secret."""
    if os.environ.get("DOCUCHAT_SMOKE") == "1":
        return "no-encrypted-volume"  # smoke data is disposable — never touch the production Keychain key for it
    bundle = Path(bundle) if bundle else KB_BUNDLE
    kb_db = Path(kb_db)
    try:
        if not bundle.exists():
            if sys.platform != "darwin" or kb_db.exists():
                return "no-encrypted-volume"  # non-mac, or a pre-existing plain store
            create_volume(bundle, passphrase or volume_passphrase())
        mount(bundle, kb_db, passphrase or volume_passphrase())
        return "mounted"
    except Exception as e:
        log.error("KB volume mount failed: %s", e)
        return f"mount-failed: {type(e).__name__}"


def eject_kb_volume(kb_db):
    """App-shutdown hook: eject the KB volume if this process mounted one."""
    return eject(kb_db)
