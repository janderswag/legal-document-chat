"""Key envelope for the encryption cycle (D-73, design doc §3).

One master key lives in the macOS login Keychain (generic password, service
``docuchat-kb``) — NEVER in a file, an env var, or git. Per-matter Data Encryption
Keys (DEKs) are wrapped by it with AES-256-GCM and stored (wrapped only) in the
catalog's ``matter_keys`` table. Matter natives/exports are encrypted at the file
layer with the matter's DEK (D-73: single encrypted volume hosts the store; the DEK
covers the per-matter file tree so destroying it is a cryptographic erase of the
originals).

Keychain access goes through the ``security`` CLI with commands fed via STDIN
(``security -i``) so key material never appears in an argv/process listing. The
Python ``keyring`` package is deliberately not used: same login-keychain storage,
one fewer dependency in the frozen app. Secure-Enclave-backed keys need a
codesigned entitlement and are a post-signing upgrade, not claimed here.

Crypto-shred primitive: ``destroy_matter_dek`` NULLs the wrapped blob and
timestamps the destruction — after that the matter's ciphertext is irrecoverable
by anyone, including us. The retention flow (routes_retention) builds the
certificate language on top of this; this module only provides the mechanism.
"""

import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag  # noqa: F401  (re-export for callers)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import catalog

KEYCHAIN_SERVICE = "docuchat-kb"
KEYCHAIN_ACCOUNT = "master-key-v1"
_DEK_AAD = b"docuchat-dek-v1"
_FILE_AAD = b"docuchat-file-v1"
MAGIC = b"DCHATENC1"  # encrypted-file header: MAGIC + 12-byte nonce + GCM ciphertext
_NONCE_LEN = 12


class KeyDestroyedError(RuntimeError):
    """The matter's DEK was crypto-shredded; its ciphertext is gone for good."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- master key (Keychain) ----------------------------------------------------

def _security(commands):
    """Run ``security -i`` with commands on STDIN (secrets never in argv)."""
    return subprocess.run(["security", "-i"], input=commands,
                          capture_output=True, text=True)


def master_key(service=KEYCHAIN_SERVICE, account=KEYCHAIN_ACCOUNT):
    """Fetch the 32-byte master key from the login Keychain, creating it on first
    use. Raises RuntimeError if the Keychain is unavailable (non-macOS / locked)."""
    r = _security(f'find-generic-password -s "{service}" -a "{account}" -w\n')
    if r.returncode == 0:
        return bytes.fromhex(r.stdout.strip())
    fresh = secrets.token_bytes(32)
    r = _security(
        f'add-generic-password -s "{service}" -a "{account}" -w "{fresh.hex()}" -U\n')
    if r.returncode != 0:
        raise RuntimeError(f"Keychain unavailable: {r.stderr.strip()}")
    return fresh


# --- DEK envelope (AES-256-GCM) -----------------------------------------------

def new_dek():
    """A fresh 32-byte Data Encryption Key."""
    return secrets.token_bytes(32)


def wrap_dek(dek, master):
    """nonce(12) + AESGCM(master).encrypt(dek). Nondeterministic by nonce."""
    nonce = secrets.token_bytes(_NONCE_LEN)
    return nonce + AESGCM(master).encrypt(nonce, dek, _DEK_AAD)


def unwrap_dek(wrapped, master):
    """Inverse of wrap_dek. Raises InvalidTag on tamper or wrong master key."""
    nonce, ct = wrapped[:_NONCE_LEN], wrapped[_NONCE_LEN:]
    return AESGCM(master).decrypt(nonce, ct, _DEK_AAD)


# --- per-matter DEKs in the catalog --------------------------------------------

_KEYS_SCHEMA = """
CREATE TABLE IF NOT EXISTS matter_keys (
    matter_slug TEXT PRIMARY KEY,
    wrapped_dek BLOB,
    created TEXT NOT NULL,
    destroyed TEXT
);
"""


def _conn(db_path=None):
    conn = catalog._connect(db_path)
    conn.executescript(_KEYS_SCHEMA)
    return conn


def ensure_matter_dek(matter_slug, master=None, db_path=None):
    """Return the matter's DEK, creating + wrapping + storing it on first use.
    Raises KeyDestroyedError if the DEK was crypto-shredded (by design there is
    no way back)."""
    master = master if master is not None else master_key()
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT wrapped_dek, destroyed FROM matter_keys WHERE matter_slug = ?",
            (matter_slug,)).fetchone()
        if row is not None:
            if row["destroyed"] is not None:
                raise KeyDestroyedError(
                    f"DEK for '{matter_slug}' was cryptographically destroyed "
                    f"at {row['destroyed']}")
            return unwrap_dek(row["wrapped_dek"], master)
        dek = new_dek()
        conn.execute(
            "INSERT INTO matter_keys (matter_slug, wrapped_dek, created) VALUES (?, ?, ?)",
            (matter_slug, wrap_dek(dek, master), _now()))
        conn.commit()
        return dek
    finally:
        conn.close()


def destroy_matter_dek(matter_slug, db_path=None):
    """Crypto-shred primitive: NULL the wrapped DEK and timestamp the destruction.
    Returns True if a live key was destroyed, False if none existed. Irreversible."""
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "UPDATE matter_keys SET wrapped_dek = NULL, destroyed = ? "
            "WHERE matter_slug = ? AND wrapped_dek IS NOT NULL",
            (_now(), matter_slug))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def dek_destroyed_at(matter_slug, db_path=None):
    """The destruction timestamp for a shredded DEK, or None (certificate input)."""
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT destroyed FROM matter_keys WHERE matter_slug = ?",
            (matter_slug,)).fetchone()
        return row["destroyed"] if row else None
    finally:
        conn.close()


# --- file-layer encryption (natives/export tree) -------------------------------

def encrypt_file(src, dst, dek):
    """Encrypt src -> dst as MAGIC + nonce + AES-256-GCM ciphertext. Whole-file
    (natives are documents, not media; the GCM tag authenticates every byte)."""
    nonce = secrets.token_bytes(_NONCE_LEN)
    ct = AESGCM(dek).encrypt(nonce, Path(src).read_bytes(), _FILE_AAD)
    Path(dst).write_bytes(MAGIC + nonce + ct)


def decrypt_file(src, dst, dek):
    """Decrypt an encrypt_file() artifact. Wrong key / tamper raises InvalidTag
    BEFORE anything is written; a non-encrypted input raises ValueError."""
    raw = Path(src).read_bytes()
    if not raw.startswith(MAGIC):
        raise ValueError(f"{src} is not a docuchat-encrypted file (missing header)")
    body = raw[len(MAGIC):]
    nonce, ct = body[:_NONCE_LEN], body[_NONCE_LEN:]
    plain = AESGCM(dek).decrypt(nonce, ct, _FILE_AAD)
    Path(dst).write_bytes(plain)
