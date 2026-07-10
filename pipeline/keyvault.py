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


def keychain_secret(account, service=KEYCHAIN_SERVICE):
    """Fetch a 32-byte secret from the login Keychain by account name, creating it
    on FIRST use only. Raises RuntimeError if the Keychain is unavailable
    (non-macOS / locked / sandboxed / ACL-denied). Used for the master key and
    the KB volume key — never for plaintext.

    SAFETY (v0.3.0 post-mortem): a failed READ is NOT the same as "item does not
    exist". The old code created a fresh key on ANY find failure and passed -U
    (update), so a locked keychain or a denied ACL prompt silently REPLACED the
    real master key — cryptographically destroying every DEK wrapped by it.
    Now: create only when the keychain explicitly says the item was not found,
    NEVER pass -U, and treat an "already exists" race as a re-read."""
    r = _security(f'find-generic-password -s "{service}" -a "{account}" -w\n')
    if r.returncode == 0:
        return bytes.fromhex(r.stdout.strip())
    if "could not be found" not in (r.stderr or ""):
        # locked / denied / sandboxed — the item may well EXIST; refuse loudly
        raise RuntimeError(
            f"Keychain read failed (NOT creating a key — the existing one may "
            f"be intact): {r.stderr.strip() or f'status {r.returncode}'}")
    fresh = secrets.token_bytes(32)
    r = _security(
        f'add-generic-password -s "{service}" -a "{account}" -w "{fresh.hex()}"\n')
    if r.returncode == 0:
        return fresh
    if "already exists" in (r.stderr or ""):
        # lost a create race — the winner's key is the real one
        r = _security(f'find-generic-password -s "{service}" -a "{account}" -w\n')
        if r.returncode == 0:
            return bytes.fromhex(r.stdout.strip())
    raise RuntimeError(f"Keychain unavailable: {r.stderr.strip()}")


def master_key(service=KEYCHAIN_SERVICE, account=KEYCHAIN_ACCOUNT):
    """The 32-byte master key. Tests that injected ``catalog.MASTER_KEY_PROVIDER``
    get their key back here too, so the whole envelope follows one injection point."""
    if service == KEYCHAIN_SERVICE and catalog.MASTER_KEY_PROVIDER is not None:
        return catalog.MASTER_KEY_PROVIDER()
    return keychain_secret(account, service=service)


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


# --- matter-native helpers (encrypt-at-rest policy + transparent reads) --------

# None = auto (encrypt natives iff the production catalog is encrypted — the signal
# that the encryption cycle is active on this install). Tests force True/False.
NATIVES_ENCRYPTION = None


def natives_encryption_active(db_path=None):
    if NATIVES_ENCRYPTION is not None:
        return NATIVES_ENCRYPTION
    return catalog.is_encrypted(Path(db_path) if db_path else catalog.DEFAULT_DB)


def is_encrypted_file(path):
    """True if the file starts with the docuchat encrypted-file magic."""
    try:
        with open(path, "rb") as f:
            return f.read(len(MAGIC)) == MAGIC
    except (FileNotFoundError, OSError):
        return False


def write_matter_file(path, data, matter_slug, db_path=None):
    """Write a native: encrypted with the matter DEK when encryption is active,
    plain otherwise. Returns True if the write was encrypted."""
    if natives_encryption_active(db_path):
        dek = ensure_matter_dek(matter_slug, db_path=db_path)
        nonce = secrets.token_bytes(_NONCE_LEN)
        ct = AESGCM(dek).encrypt(nonce, data, _FILE_AAD)
        Path(path).write_bytes(MAGIC + nonce + ct)
        return True
    Path(path).write_bytes(data)
    return False


def read_matter_file(path, matter_slug, db_path=None):
    """Read a native's PLAINTEXT bytes, transparently decrypting encrypted files
    (pre-encryption plain files read as-is). Raises KeyDestroyedError after a
    crypto-shred — by design that content is gone."""
    raw = Path(path).read_bytes()
    if not raw.startswith(MAGIC):
        return raw
    dek = ensure_matter_dek(matter_slug, db_path=db_path)
    body = raw[len(MAGIC):]
    return AESGCM(dek).decrypt(body[:_NONCE_LEN], body[_NONCE_LEN:], _FILE_AAD)


# --- connector credentials (v0.3.0, D-81) ---------------------------------------
# API keys/tokens for user-created connections are sealed with the SAME Keychain
# master key (never a file, never plaintext in the catalog). Distinct AAD so a
# credential blob can never be confused with a wrapped DEK.

_SECRET_AAD = b"docuchat-conn-v1"


def encrypt_secret(data):
    """Seal connector credential bytes: nonce(12) + AESGCM(master).encrypt."""
    nonce = secrets.token_bytes(_NONCE_LEN)
    return nonce + AESGCM(master_key()).encrypt(nonce, data, _SECRET_AAD)


def decrypt_secret(blob):
    """Unseal encrypt_secret() output. Raises InvalidTag on tamper/wrong key."""
    return AESGCM(master_key()).decrypt(blob[:_NONCE_LEN], blob[_NONCE_LEN:],
                                        _SECRET_AAD)


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
