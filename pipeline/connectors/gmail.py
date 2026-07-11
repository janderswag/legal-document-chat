"""Gmail — matter email by label, pulled over IMAP with a Google app password.

Verified against support.google.com/mail/answer/185833 and
developers.google.com/workspace/gmail/imap (2026-07-10, research_email.json):
IMAP over SSL at imap.gmail.com:993, signing in with the full Gmail address
and a 16-character app password the user self-serves at
myaccount.google.com/apppasswords (requires 2-Step Verification). Gmail
labels appear as IMAP mailboxes: the user creates a label, applies it to the
matter emails, and docuchat pulls exactly that mailbox. Messages arrive as
raw RFC822 bytes and are stored as .eml files — docuchat already ingests
.eml natively, attachments included.

Pull-only, strictly: every SELECT is readonly (IMAP EXAMINE), so nothing is
ever marked read and the mailbox is never modified. A single pass lists at
most 500 NEW messages, oldest first — already-imported UIDs are excluded
BEFORE the cap (council 2026-07-11 F1), so repeated passes walk a label of
any size and new mail is always reachable once the backlog drains. The old
behavior capped the raw UID list, which permanently pinned sync to the
oldest 500 messages of a large label.

This is the ONE adapter allowed to bypass connectors.request (stdlib imaplib,
no HTTP). It maps imaplib/socket failures onto the shared taxonomy itself:
authentication failures -> ConnectorAuthError, connection/transport failures
-> ConnectorUnavailable.
"""

import email
import email.header
import email.utils
import imaplib
import re
import ssl

import connectors

HOST = "imap.gmail.com"
MAX_MESSAGES = 500          # per-pass cap, oldest first
_HEADER_BATCH = 100         # UIDs per header-fetch round trip

SERVICE = {
    "slug": "gmail",
    "name": "Gmail",
    "category": "Email",
    "blurb": "Matter email pulled by Gmail label, attachments included",
    "fields": [
        {"key": "email", "label": "Gmail address"},
        {"key": "app_password", "label": "App password (16 characters)",
         "secret": True},
        {"key": "label", "label": "Gmail label to import",
         "default": "docuchat"},
    ],
    "key_steps": [
        "Turn on 2-Step Verification for your Google Account "
        "(myaccount.google.com > Security), if it is not already on",
        "Go to myaccount.google.com/apppasswords, enter a name like "
        "'docuchat', and click Create",
        "Copy the 16-character app password Google shows — it appears "
        "only once",
        "In Gmail, create a label (e.g. 'docuchat') and apply it to the "
        "emails you want imported for this matter",
        "Enter your Gmail address, the app password, and that label name "
        "here",
    ],
    "plan_note": "Needs 2-Step Verification plus an app password. App "
                 "passwords are revoked whenever the Google password changes "
                 "(reconnect with a new one), and are not available on most "
                 "Google Workspace accounts or accounts with Advanced "
                 "Protection.",
    "docs_url": "https://support.google.com/mail/answer/185833",
}


# --- IMAP plumbing with the error taxonomy applied -----------------------------

def _label_name(creds):
    return (creds.get("label") or "docuchat").strip() or "docuchat"


def _connect(creds):
    try:
        # Verify the server certificate + hostname. IMAP4_SSL with no context
        # falls back to an UNVERIFIED context (CERT_NONE), which would let a
        # network MITM present any cert, capture the app password, and read the
        # mailbox. create_default_context() = CERT_REQUIRED + check_hostname.
        conn = imaplib.IMAP4_SSL(HOST, ssl_context=ssl.create_default_context())
    except (OSError, ssl.SSLError):
        raise connectors.ConnectorUnavailable(
            "could not reach Gmail (imap.gmail.com) — check the internet "
            "connection and try again")
    try:
        # Google displays the app password with spaces ("xxxx xxxx xxxx xxxx").
        conn.login(creds["email"].strip(),
                   creds["app_password"].strip().replace(" ", ""))
    except imaplib.IMAP4.error:
        _logout(conn)
        raise connectors.ConnectorAuthError(
            "Gmail rejected this sign-in — check the address and app "
            "password. App passwords are revoked when the Google password "
            "changes; create a new one at myaccount.google.com/apppasswords")
    except (OSError, ssl.SSLError):
        raise connectors.ConnectorUnavailable(
            "the connection to Gmail dropped while signing in — try again")
    return conn


def _logout(conn):
    try:
        conn.logout()
    except Exception:
        pass


def _quote_mailbox(name):
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


_LIST_RE = re.compile(r'\([^)]*\) "[^"]*" (.+)$')


def _mailbox_from_list_line(raw):
    """b'(\\HasNoChildren) "/" "docuchat"' -> 'docuchat'."""
    if isinstance(raw, tuple):          # literal continuation form
        raw = raw[0]
    m = _LIST_RE.match(raw.decode("utf-8", "replace").strip())
    if not m:
        return None
    name = m.group(1).strip()
    if name.startswith('"') and name.endswith('"'):
        name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return name


def _select_label(conn, label):
    """EXAMINE (readonly) the label mailbox; returns its UIDVALIDITY."""
    try:
        typ, _ = conn.select(_quote_mailbox(label), readonly=True)
    except imaplib.IMAP4.error:
        typ = "NO"
    if typ != "OK":
        raise connectors.ConnectorAccessError(
            f"could not open the Gmail label '{label}' — create the label "
            "in Gmail, apply it to the matter emails, and try again")
    try:
        _, data = conn.response("UIDVALIDITY")
        return (data[0] or b"0").decode()
    except Exception:
        return "0"


def _decode_header(value):
    if not value:
        return ""
    parts = []
    for text, enc in email.header.decode_header(value):
        if isinstance(text, bytes):
            text = text.decode(enc or "utf-8", "replace")
        parts.append(text)
    return "".join(parts).strip()


def _date_parts(msg):
    """(iso_datetime, yyyy-mm-dd stamp) from the Date header, best effort."""
    try:
        dt = email.utils.parsedate_to_datetime(msg.get("Date") or "")
        iso = dt.isoformat()
        return iso, iso[:10]
    except (TypeError, ValueError):
        return None, ""


# --- adapter interface ----------------------------------------------------------

def test(creds):
    conn = _connect(creds)
    try:
        label = _label_name(creds)
        try:
            typ, boxes = conn.list()
        except (imaplib.IMAP4.error, OSError):
            raise connectors.ConnectorUnavailable(
                "Gmail did not answer the mailbox listing — try again")
        names = {_mailbox_from_list_line(b) for b in (boxes or []) if b}
        if typ != "OK" or label not in names:
            raise connectors.ConnectorAccessError(
                f"signed in, but no Gmail label named '{label}' was found — "
                "create the label in Gmail, apply it to the matter emails, "
                "and try again")
        return f"{creds['email'].strip()} — label '{label}' ready"
    finally:
        _logout(conn)


def list_items(creds, since=None, exclude_ids=None):
    conn = _connect(creds)
    try:
        label = _label_name(creds)
        uidvalidity = _select_label(conn, label)
        try:
            typ, data = conn.uid("SEARCH", None, "ALL")
        except (imaplib.IMAP4.error, OSError):
            typ, data = "NO", None
        if typ != "OK":
            raise connectors.ConnectorUnavailable(
                "Gmail did not answer the message search — try again")
        # UID SEARCH returns UIDs ascending (oldest first). Drop the already-
        # imported ones BEFORE capping (F1): the cap bounds one pass's work,
        # never the reachable mailbox.
        uids = [u.decode() for u in (data[0] or b"").split()]
        if exclude_ids:
            seen = set(exclude_ids)
            uids = [u for u in uids if f"{uidvalidity}:{u}" not in seen]
        uids = uids[:MAX_MESSAGES]
        items = []
        for i in range(0, len(uids), _HEADER_BATCH):
            batch = uids[i:i + _HEADER_BATCH]
            try:
                typ, parts = conn.uid(
                    "FETCH", ",".join(batch),
                    "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE FROM)])")
            except (imaplib.IMAP4.error, OSError):
                typ, parts = "NO", None
            if typ != "OK":
                raise connectors.ConnectorUnavailable(
                    "Gmail did not return the message headers — try again")
            for part in parts or []:
                if not isinstance(part, tuple) or len(part) < 2:
                    continue
                m = re.search(rb"UID (\d+)", part[0])
                if not m:
                    continue
                uid = m.group(1).decode()
                msg = email.message_from_bytes(part[1])
                subject = _decode_header(msg.get("Subject")) or "(no subject)"
                iso, stamp = _date_parts(msg)
                items.append({
                    "id": f"{uidvalidity}:{uid}",
                    "name": f"{subject} ({stamp})" if stamp else subject,
                    "kind": "email",
                    "modified": iso,
                    "meta": {"uid": uid, "uidvalidity": uidvalidity,
                             "label": label, "subject": subject,
                             "from": _decode_header(msg.get("From")),
                             "date": iso},
                })
        return items
    finally:
        _logout(conn)


def fetch_item(creds, item):
    conn = _connect(creds)
    try:
        meta = item.get("meta") or {}
        label = meta.get("label") or _label_name(creds)
        _select_label(conn, label)                      # readonly, always
        uid = meta.get("uid") or item["id"].rsplit(":", 1)[-1]
        try:
            typ, parts = conn.uid("FETCH", uid, "(RFC822)")
        except (imaplib.IMAP4.error, OSError):
            typ, parts = "NO", None
        raw = None
        for part in parts or []:
            if isinstance(part, tuple) and len(part) >= 2 and part[1]:
                raw = part[1]
                break
        if typ != "OK" or raw is None:
            raise connectors.ConnectorUnavailable(
                "Gmail did not return this message — it may have been "
                "deleted or the label removed; refresh and try again")
        msg = email.message_from_bytes(raw)
        subject = _decode_header(msg.get("Subject")) or "Email"
        iso, stamp = _date_parts(msg)
        prov = {
            "service": "gmail",
            "title": subject,
            "author": _decode_header(msg.get("From")),
            "recipients": _decode_header(msg.get("To")),
            "date": iso,
            "label": label,
            "message_id": (msg.get("Message-ID") or "").strip(),
        }
        base = f"{subject} ({stamp})" if stamp else subject
        return f"{base}.eml", raw, prov
    finally:
        _logout(conn)
