"""Adapter proofs for the email + file-storage batch (v0.3.0, D-81):
gmail (IMAP app password), slack (self-created app token), nextcloud
(WebDAV app password) — against the vendors' DOCUMENTED shapes from the
2026-07-10 research pass. No network.

HTTP adapters (slack, nextcloud) reuse the shared MockVendor harness from
test_adapters. Gmail is the one non-HTTP adapter (stdlib imaplib), so it is
proven against a scripted FakeIMAP via unittest.mock: readonly-only selects,
raw RFC822 -> .eml round trip, and imaplib error -> taxonomy mapping.

ShareFile IS built (connectors/sharefile.py, proven separately in
test_adapters_sharefile.py) once connectors.request grew a form_body param
for its form-encoded password-grant token request.
"""

import imaplib
import sys
import unittest
from pathlib import Path
from unittest import mock

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import connectors  # noqa: E402

from tests.test_adapters import (  # noqa: E402
    FakeResponse, MockVendor, fetch_contract_check, service_contract_check)


# =============================== Gmail (IMAP) ===================================

RAW_MSG_1 = (b"Subject: Pemberton engagement letter\r\n"
             b"From: Ana Torres <ana@firm.example>\r\n"
             b"To: jake@firm.example\r\n"
             b"Date: Tue, 01 Jul 2026 10:00:00 +0000\r\n"
             b"Message-ID: <m1@mail.gmail.example>\r\n"
             b"MIME-Version: 1.0\r\n"
             b"Content-Type: text/plain\r\n"
             b"\r\n"
             b"Please find the engagement letter attached.\r\n")

RAW_MSG_2 = (b"Subject: Re: discovery schedule\r\n"
             b"From: jake@firm.example\r\n"
             b"To: ana@firm.example\r\n"
             b"Date: Wed, 02 Jul 2026 09:30:00 +0000\r\n"
             b"Message-ID: <m2@mail.gmail.example>\r\n"
             b"\r\n"
             b"Confirmed for Thursday.\r\n")


def _headers_only(raw):
    return raw.split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n"


class FakeIMAP:
    """Scripted imap.gmail.com: a 'docuchat' label mailbox holding messages."""

    PASSWORD = "abcdabcdabcdabcd"
    UIDVALIDITY = b"9942"

    def __init__(self, messages=None):
        self.messages = messages or {b"11": RAW_MSG_1, b"12": RAW_MSG_2}
        self.logins = []
        self.selects = []           # (mailbox, readonly)
        self.logged_out = False

    def __call__(self, host, ssl_context=None):  # stands in for IMAP4_SSL
        self.host = host
        self.ssl_context = ssl_context
        return self

    def login(self, user, password):
        self.logins.append((user, password))
        if password != self.PASSWORD:
            raise imaplib.IMAP4.error(
                b"[AUTHENTICATIONFAILED] Invalid credentials (Failure)")
        return "OK", [b"authenticated"]

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"',
                      b'(\\HasChildren \\Noselect) "/" "[Gmail]"',
                      b'(\\HasNoChildren) "/" "docuchat"']

    def select(self, mailbox, readonly=False):
        self.selects.append((mailbox, readonly))
        if mailbox != '"docuchat"':
            return "NO", [b"[NONEXISTENT] Unknown Mailbox"]
        return "OK", [b"%d" % len(self.messages)]

    def response(self, key):
        if key == "UIDVALIDITY":
            return key, [self.UIDVALIDITY]
        return key, [None]

    def uid(self, cmd, *args):
        args = [a for a in args if a is not None]
        if cmd == "SEARCH":
            uids = sorted(self.messages, key=int)
            return "OK", [b" ".join(uids)]
        if cmd == "FETCH":
            uid_set, spec = args
            out = []
            for u in uid_set.split(","):
                raw = self.messages.get(u.encode())
                if raw is None:
                    continue
                payload = raw if "RFC822" in spec else _headers_only(raw)
                out.append((b"1 (UID " + u.encode() + b" ...", payload))
                out.append(b")")
            return "OK", out
        raise AssertionError(f"unexpected IMAP command: {cmd}")

    def logout(self):
        self.logged_out = True
        return "BYE", [b"bye"]


class TestGmail(unittest.TestCase):
    CREDS = {"email": "jake@gmail.example",
             "app_password": "abcd abcd abcd abcd",   # as Google displays it
             "label": "docuchat"}

    def _mod(self):
        from connectors import gmail
        return gmail

    def _patch(self, fake):
        return mock.patch.object(self._mod().imaplib, "IMAP4_SSL", fake)

    def test_service_metadata(self):
        service_contract_check(self, self._mod())
        self.assertEqual(self._mod().SERVICE["slug"], "gmail")
        # the label workflow must be spelled out for the user
        steps = " ".join(self._mod().SERVICE["key_steps"]).lower()
        self.assertIn("label", steps)
        self.assertIn("apppasswords", steps)

    def test_login_and_label_check(self):
        fake = FakeIMAP()
        with self._patch(fake):
            label = self._mod().test(self.CREDS)
        self.assertEqual(fake.host, "imap.gmail.com")
        # display spaces stripped from the app password before login
        self.assertEqual(fake.logins[0],
                         ("jake@gmail.example", "abcdabcdabcdabcd"))
        self.assertIn("docuchat", label)
        self.assertTrue(fake.logged_out)

    def test_tls_context_verifies_cert_and_hostname(self):
        # Regression: IMAP4_SSL with no context accepts ANY cert (CERT_NONE),
        # leaking the app password to a network MITM. We must pass a verifying
        # context before the app password is ever sent.
        import ssl
        fake = FakeIMAP()
        with self._patch(fake):
            self._mod().test(self.CREDS)
        self.assertIsInstance(fake.ssl_context, ssl.SSLContext)
        self.assertEqual(fake.ssl_context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(fake.ssl_context.check_hostname)

    def test_missing_label_is_access_error(self):
        fake = FakeIMAP()
        with self._patch(fake):
            with self.assertRaises(connectors.ConnectorAccessError):
                self._mod().test(dict(self.CREDS, label="nosuchlabel"))

    def test_bad_app_password_maps_to_auth_error(self):
        fake = FakeIMAP()
        with self._patch(fake):
            with self.assertRaises(connectors.ConnectorAuthError):
                self._mod().test(dict(self.CREDS, app_password="wrong"))

    def test_connection_failure_maps_to_unavailable(self):
        def boom(host, ssl_context=None):
            raise OSError("network unreachable")
        with mock.patch.object(self._mod().imaplib, "IMAP4_SSL", boom):
            with self.assertRaises(connectors.ConnectorUnavailable):
                self._mod().test(self.CREDS)

    def test_list_is_readonly_and_maps_headers(self):
        fake = FakeIMAP()
        with self._patch(fake):
            items = self._mod().list_items(self.CREDS)
        for mailbox, readonly in fake.selects:
            self.assertTrue(readonly, "SELECT must always be readonly")
        self.assertEqual([i["id"] for i in items], ["9942:11", "9942:12"])
        self.assertIn("Pemberton engagement letter", items[0]["name"])
        self.assertIn("2026-07-01", items[0]["name"])
        self.assertEqual(items[0]["kind"], "email")
        self.assertEqual(items[0]["meta"]["uid"], "11")

    def test_list_caps_at_500_oldest_first(self):
        messages = {str(u).encode():
                    (b"Subject: msg %d\r\nDate: Tue, 01 Jul 2026 "
                     b"10:00:00 +0000\r\n\r\nbody\r\n" % u)
                    for u in range(1, 601)}
        fake = FakeIMAP(messages=messages)
        with self._patch(fake):
            items = self._mod().list_items(self.CREDS)
        self.assertEqual(len(items), 500)
        self.assertEqual(items[0]["id"], "9942:1")
        self.assertEqual(items[-1]["id"], "9942:500")

    def test_fetch_round_trips_eml_readonly(self):
        fake = FakeIMAP()
        item = {"id": "9942:11", "name": "Pemberton engagement letter",
                "kind": "email", "modified": "2026-07-01T10:00:00+00:00",
                "meta": {"uid": "11", "uidvalidity": "9942",
                         "label": "docuchat"}}
        with self._patch(fake):
            name, body, prov = self._mod().fetch_item(self.CREDS, item)
        fetch_contract_check(self, name, body, prov)
        self.assertTrue(name.endswith(".eml"))
        self.assertEqual(body, RAW_MSG_1)          # raw RFC822, untouched
        for mailbox, readonly in fake.selects:
            self.assertTrue(readonly, "fetch must never open read-write")
        self.assertEqual(prov["title"], "Pemberton engagement letter")
        self.assertIn("ana@firm.example", prov["author"])
        self.assertEqual(prov["message_id"], "<m1@mail.gmail.example>")


# ================================== Slack =======================================

class TestSlack(unittest.TestCase):
    CREDS = {"token": "xoxp-test-token"}
    API = "https://slack.com/api"
    FILE_PDF = {"id": "F1", "name": "engagement.pdf",
                "title": "Engagement letter", "created": 1751364000,
                "timestamp": 1751364000, "user": "U1", "channels": ["C1"],
                "groups": [], "permalink": "https://firm.slack.example/f/F1",
                "url_private": "https://files.slack.example/files-pri/T1-F1/engagement.pdf"}
    FILE_PNG = {"id": "F2", "name": "whiteboard.png", "created": 1751364100,
                "user": "U1", "channels": ["C1"],
                "url_private": "https://files.slack.example/files-pri/T1-F2/whiteboard.png"}
    FILE_DOCX = {"id": "F3", "name": "memo.docx", "title": "Memo",
                 "created": 1751450400, "user": "U2", "channels": [],
                 "groups": ["G1"],
                 "permalink": "https://firm.slack.example/f/F3",
                 "url_private": "https://files.slack.example/files-pri/T1-F3/memo.docx"}

    def _mod(self):
        from connectors import slack
        return slack

    def _routes(self):
        channels = FakeResponse(json_data={
            "ok": True,
            "channels": [{"id": "C1", "name": "matter-pemberton"},
                         {"id": "G1", "name": "privileged-notes"}],
            "response_metadata": {"next_cursor": ""}})

        def files_route(call):
            if call["params"].get("page") == "1":
                return FakeResponse(json_data={
                    "ok": True, "files": [self.FILE_PDF, self.FILE_PNG],
                    "paging": {"page": 1, "pages": 2}})
            return FakeResponse(json_data={
                "ok": True, "files": [self.FILE_DOCX],
                "paging": {"page": 2, "pages": 2}})

        return [("GET", f"{self.API}/conversations.list", channels),
                ("GET", f"{self.API}/files.list", files_route)]

    def test_service_metadata(self):
        service_contract_check(self, self._mod())
        self.assertEqual(self._mod().SERVICE["slug"], "slack")
        steps = " ".join(self._mod().SERVICE["key_steps"])
        for scope in ("channels:history", "channels:read", "files:read",
                      "groups:read"):
            self.assertIn(scope, steps)

    def test_auth_test_sends_bearer_and_labels(self):
        ok = FakeResponse(json_data={"ok": True, "user": "jake",
                                     "team": "firm"})
        with MockVendor([("POST", f"{self.API}/auth.test", ok)]) as v:
            label = self._mod().test(self.CREDS)
        self.assertEqual(v.calls[0]["headers"]["Authorization"],
                         "Bearer xoxp-test-token")
        self.assertIn("jake", label)
        self.assertIn("firm", label)

    def test_ok_false_invalid_auth_maps_to_auth_error(self):
        # Slack's signature move: HTTP 200 with ok:false in the body
        bad = FakeResponse(json_data={"ok": False, "error": "invalid_auth"})
        with MockVendor([("POST", f"{self.API}/auth.test", bad)]):
            with self.assertRaises(connectors.ConnectorAuthError):
                self._mod().test(self.CREDS)

    def test_ok_false_missing_scope_maps_to_access_error(self):
        bad = FakeResponse(json_data={"ok": False, "error": "missing_scope"})
        with MockVendor([("POST", f"{self.API}/auth.test", bad)]):
            with self.assertRaises(connectors.ConnectorAccessError):
                self._mod().test(self.CREDS)

    def test_list_paginates_filters_and_names_channels(self):
        with MockVendor(self._routes()) as v:
            items = self._mod().list_items(self.CREDS)
        self.assertEqual([i["id"] for i in items], ["F1", "F3"])  # png dropped
        self.assertEqual(items[0]["name"], "Engagement letter")
        self.assertEqual(items[0]["meta"]["channel_names"],
                         ["matter-pemberton"])
        self.assertEqual(items[1]["meta"]["channel_names"],
                         ["privileged-notes"])
        pages = [c["params"].get("page") for c in v.calls
                 if "files.list" in c["url"]]
        self.assertEqual(pages, ["1", "2"])

    def test_fetch_downloads_url_private_with_bearer(self):
        meta = dict(self.FILE_PDF, channel_names=["matter-pemberton"])
        item = {"id": "F1", "name": "Engagement letter", "kind": "file",
                "modified": None, "meta": meta}
        pdf = FakeResponse(content=b"%PDF-1.4 fake body")
        with MockVendor([("GET", "https://files.slack.example/", pdf)]) as v:
            name, body, prov = self._mod().fetch_item(self.CREDS, item)
        fetch_contract_check(self, name, body, prov)
        self.assertEqual(name, "engagement.pdf")   # real extension kept
        self.assertEqual(body, b"%PDF-1.4 fake body")
        # without the Bearer header Slack returns an HTML login page
        self.assertEqual(v.calls[0]["headers"]["Authorization"],
                         "Bearer xoxp-test-token")
        self.assertEqual(prov["author"], "U1")
        self.assertEqual(prov["url"], "https://firm.slack.example/f/F1")
        self.assertEqual(prov["channels"], ["matter-pemberton"])

    def test_http_401_maps_to_auth_error(self):
        with MockVendor([("POST", f"{self.API}/auth.test",
                          FakeResponse(401))]):
            with self.assertRaises(connectors.ConnectorAuthError):
                self._mod().test(self.CREDS)


# ================================ Nextcloud =====================================

MS_TEST = b"""<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
 <d:response><d:href>/remote.php/dav/files/jake/</d:href>
  <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop>
   <d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>
</d:multistatus>"""

MS_ROOT = b"""<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">
 <d:response><d:href>/remote.php/dav/files/jake/Matters/</d:href>
  <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop>
   <d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>
 <d:response>
  <d:href>/remote.php/dav/files/jake/Matters/engagement%20letter.pdf</d:href>
  <d:propstat><d:prop>
    <d:getlastmodified>Tue, 01 Jul 2026 10:00:00 GMT</d:getlastmodified>
    <d:getcontenttype>application/pdf</d:getcontenttype>
    <d:resourcetype/></d:prop>
   <d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>
 <d:response><d:href>/remote.php/dav/files/jake/Matters/whiteboard.png</d:href>
  <d:propstat><d:prop>
    <d:getlastmodified>Tue, 01 Jul 2026 11:00:00 GMT</d:getlastmodified>
    <d:resourcetype/></d:prop>
   <d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>
 <d:response><d:href>/remote.php/dav/files/jake/Matters/Case%20Files/</d:href>
  <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop>
   <d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>
</d:multistatus>"""

MS_SUB = b"""<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
 <d:response><d:href>/remote.php/dav/files/jake/Matters/Case%20Files/</d:href>
  <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop>
   <d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>
 <d:response>
  <d:href>/remote.php/dav/files/jake/Matters/Case%20Files/memo.docx</d:href>
  <d:propstat><d:prop>
    <d:getlastmodified>Wed, 02 Jul 2026 09:00:00 GMT</d:getlastmodified>
    <d:resourcetype/></d:prop>
   <d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>
</d:multistatus>"""


class TestNextcloud(unittest.TestCase):
    CREDS = {"server_url": "https://cloud.example.test", "username": "jake",
             "app_password": "nc-app-pass", "folder": "/Matters"}
    DAV = "https://cloud.example.test/remote.php/dav/files/jake"

    def _mod(self):
        from connectors import nextcloud
        return nextcloud

    def _propfind_route(self):
        def route(call):
            if call["url"].endswith("/Case%20Files/"):
                return FakeResponse(207, content=MS_SUB)
            if call["url"].endswith("/Matters/"):
                return FakeResponse(207, content=MS_ROOT)
            return FakeResponse(207, content=MS_TEST)
        return ("PROPFIND", self.DAV, route)

    def test_service_metadata(self):
        service_contract_check(self, self._mod())
        self.assertEqual(self._mod().SERVICE["slug"], "nextcloud")
        steps = " ".join(self._mod().SERVICE["key_steps"]).lower()
        self.assertIn("security", steps)
        self.assertIn("app password", steps)

    def test_probe_sends_basic_auth_depth_zero(self):
        with MockVendor([self._propfind_route()]) as v:
            label = self._mod().test(self.CREDS)
        self.assertEqual(v.calls[0]["method"], "PROPFIND")
        self.assertEqual(v.calls[0]["url"], self.DAV + "/")
        self.assertEqual(v.calls[0]["auth"], ("jake", "nc-app-pass"))
        self.assertEqual(v.calls[0]["headers"]["Depth"], "0")
        self.assertIn("jake", label)
        self.assertIn("cloud.example.test", label)

    def test_list_walks_depth_one_and_filters(self):
        with MockVendor([self._propfind_route()]) as v:
            items = self._mod().list_items(self.CREDS)
        self.assertEqual([i["id"] for i in items],
                         ["/Matters/engagement letter.pdf",
                          "/Matters/Case Files/memo.docx"])   # png dropped
        self.assertEqual(items[0]["name"], "engagement letter.pdf")
        self.assertEqual(items[0]["meta"]["getlastmodified"],
                         "Tue, 01 Jul 2026 10:00:00 GMT")
        # depth-1 walk: root folder then the (url-quoted) subfolder
        self.assertEqual([c["url"] for c in v.calls],
                         [self.DAV + "/Matters/",
                          self.DAV + "/Matters/Case%20Files/"])
        for c in v.calls:
            self.assertEqual(c["headers"]["Depth"], "1")
            self.assertEqual(c["auth"], ("jake", "nc-app-pass"))

    def test_fetch_gets_quoted_path_with_auth(self):
        item = {"id": "/Matters/Case Files/memo.docx", "name": "memo.docx",
                "kind": "file", "modified": "Wed, 02 Jul 2026 09:00:00 GMT",
                "meta": {"path": "/Matters/Case Files/memo.docx",
                         "getlastmodified": "Wed, 02 Jul 2026 09:00:00 GMT"}}
        blob = FakeResponse(content=b"PK docx bytes")
        with MockVendor([("GET", self.DAV, blob)]) as v:
            name, body, prov = self._mod().fetch_item(self.CREDS, item)
        fetch_contract_check(self, name, body, prov)
        self.assertEqual(name, "memo.docx")
        self.assertEqual(body, b"PK docx bytes")
        self.assertEqual(v.calls[0]["url"],
                         self.DAV + "/Matters/Case%20Files/memo.docx")
        self.assertEqual(v.calls[0]["auth"], ("jake", "nc-app-pass"))
        self.assertEqual(prov["path"], "/Matters/Case Files/memo.docx")
        self.assertEqual(prov["date"], "Wed, 02 Jul 2026 09:00:00 GMT")

    def test_bad_app_password_maps_to_auth_error(self):
        with MockVendor([("PROPFIND", self.DAV, FakeResponse(401))]):
            with self.assertRaises(connectors.ConnectorAuthError):
                self._mod().test(self.CREDS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
