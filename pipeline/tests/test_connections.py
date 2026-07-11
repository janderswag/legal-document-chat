"""v0.3.0 (D-81) proof: user-keyed connections — sealed credentials, tested-
before-stored keys, imports through the upload path with provenance, dedupe by
source id, disconnect-deletes-credential, and honest error surfaces.

The suite runs against a FAKE adapter injected into the registry — no network,
no real vendor. Adapter-specific behavior lives in test_adapters.py; this file
proves the framework contract every adapter inherits.
"""

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import connectors  # noqa: E402
import connsync  # noqa: E402
import ingest_worker  # noqa: E402
import keyvault  # noqa: E402
import routes_kb  # noqa: E402
import api  # noqa: E402

client = TestClient(api.app)

TEST_KEY = b"\x07" * 32


def make_fake_adapter():
    """A minimal in-memory vendor: two text notes and one unsupported file."""
    mod = types.SimpleNamespace()
    mod.SERVICE = {
        "slug": "fakevendor", "name": "Fake Vendor", "category": "Testing",
        "blurb": "test fixture", "fields": [{"key": "api_key", "label": "API key",
                                             "secret": True}],
        "key_steps": ["step one"], "plan_note": "", "docs_url": "https://example.test",
    }
    mod.calls = []

    def test(creds):
        mod.calls.append("test")
        if creds.get("api_key") != "good-key":
            raise connectors.ConnectorAuthError("the service rejected this key")
        return "tester@example.test"

    def list_items(creds, since=None):
        mod.calls.append("list")
        return [
            {"id": "n1", "name": "Board notes.txt", "kind": "note",
             "modified": "2026-07-01", "meta": {}},
            {"id": "n2", "name": "Call transcript.txt", "kind": "transcript",
             "modified": "2026-07-02", "meta": {}},
            {"id": "n3", "name": "binary.blob", "kind": "file",
             "modified": "2026-07-03", "meta": {}},
        ]

    def fetch_item(creds, item):
        mod.calls.append(f"fetch:{item['id']}")
        return (item["name"], f"SYNTHETIC body of {item['id']}".encode(),
                {"author": "Fake Author", "title": item["name"]})

    mod.test, mod.list_items, mod.fetch_item = test, list_items, fetch_item
    return mod


class ConnectionTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        self._docs, routes_kb.KB_DOCS = routes_kb.KB_DOCS, self.tmp / "kb"
        self._mkp = catalog.MASTER_KEY_PROVIDER
        catalog.MASTER_KEY_PROVIDER = lambda: TEST_KEY
        self._reg, connectors._REGISTRY = connectors._REGISTRY, {}
        self.fake = make_fake_adapter()
        connectors._REGISTRY["fakevendor"] = self.fake
        self._enq, ingest_worker.enqueue = ingest_worker.enqueue, \
            lambda *a, **k: self.enqueued.append(a) or 1
        self.enqueued = []
        connsync._jobs.clear()

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat
        routes_kb.KB_DOCS = self._docs
        catalog.MASTER_KEY_PROVIDER = self._mkp
        connectors._REGISTRY = self._reg
        ingest_worker.enqueue = self._enq

    def _connect_fake(self, **over):
        body = {"service": "fakevendor", "credentials": {"api_key": "good-key"},
                "matter": "unfiled", "sync": False}
        body.update(over)
        r = client.post("/connections", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()


class TestConnectionLifecycle(ConnectionTestBase):
    def test_services_lists_registry_metadata(self):
        svcs = client.get("/connections/services").json()["services"]
        self.assertTrue(any(s["slug"] == "fakevendor" and s["key_steps"]
                            for s in svcs))

    def test_bad_key_never_stored(self):
        r = client.post("/connections", json={
            "service": "fakevendor", "credentials": {"api_key": "wrong"}})
        self.assertEqual(r.status_code, 400)
        self.assertIn("rejected", r.json()["detail"])
        self.assertEqual(catalog.list_connections(), [])

    def test_missing_field_rejected_without_calling_vendor(self):
        r = client.post("/connections", json={
            "service": "fakevendor", "credentials": {}})
        self.assertEqual(r.status_code, 400)
        self.assertIn("api_key", r.json()["detail"])
        self.assertNotIn("test", self.fake.calls)

    def test_connect_stores_sealed_credential_only(self):
        row = self._connect_fake()
        self.assertEqual(row["label"], "tester@example.test")
        self.assertNotIn("credential", row)
        # ciphertext at rest: the raw catalog file never contains the key
        raw = (self.tmp / "cat.db").read_bytes()
        self.assertNotIn(b"good-key", raw)
        # ...but connsync can unseal it
        full = catalog.get_connection(row["id"])
        creds = json.loads(keyvault.decrypt_secret(full["credential"]))
        self.assertEqual(creds["api_key"], "good-key")

    def test_unknown_service_is_400(self):
        r = client.post("/connections", json={
            "service": "nope", "credentials": {"api_key": "x"}})
        self.assertEqual(r.status_code, 400)

    def test_remove_deletes_credential_row(self):
        row = self._connect_fake()
        client.post("/connections/remove", json={"id": row["id"]})
        self.assertIsNone(catalog.get_connection(row["id"]))
        self.assertEqual(client.get("/connections").json()["connections"], [])


class TestImportEngine(ConnectionTestBase):
    def test_import_flows_into_document_hub_with_provenance(self):
        row = self._connect_fake()
        summary = connsync.run_import(row["id"])
        self.assertEqual(summary, {"imported": 2, "skipped": 1,
                                   "attachments": 0, "already": 0})
        docs = catalog.list_documents("unfiled")
        names = sorted(d["filename"] for d in docs)
        self.assertEqual(names, ["Board notes.txt", "Call transcript.txt"])
        prov = json.loads(docs[0]["source_json"])
        self.assertEqual(prov["service"], "fakevendor")
        self.assertEqual(prov["author"], "Fake Author")
        self.assertIn("source_id", prov)
        self.assertEqual(len(self.enqueued), 2)      # ingest queued, not inline
        # managed copies exist and the vendor originals were never touched (pull-only)
        for d in docs:
            self.assertTrue(Path(d["stored_path"]).exists())

    def test_second_import_dedupes_by_source_id(self):
        row = self._connect_fake()
        connsync.run_import(row["id"])
        summary = connsync.run_import(row["id"])
        self.assertEqual(summary["imported"], 0)
        self.assertEqual(summary["already"], 3)
        self.assertEqual(len(catalog.list_documents("unfiled")), 2)

    def test_configured_matter_is_a_suggestion_never_a_target(self):
        # Owner decision #4 (council 2026-07-11, Sam's option a): imports ALWAYS
        # land in Unfiled - a configured matter survives only as the suggestion
        # chip the attorney confirms. Auto-filing into a matter is the ethics
        # defect (a synced tray can contaminate the wrong client's matter).
        catalog.create_matter("Pemberton MSA")
        row = self._connect_fake(matter="pemberton-msa")
        connsync.run_import(row["id"])
        self.assertEqual(catalog.list_documents("pemberton-msa"), [])
        docs = catalog.list_documents("unfiled")
        self.assertEqual(len(docs), 2)
        for d in docs:
            prov = json.loads(d["source_json"])
            self.assertEqual(prov["suggested_matter"], "pemberton-msa")

    def test_import_error_recorded_on_row(self):
        row = self._connect_fake()

        def broken(creds, since=None):
            raise connectors.ConnectorRateLimited("the service is rate-limiting")
        self.fake.list_items = broken
        with self.assertRaises(connectors.ConnectorRateLimited):
            connsync.run_import(row["id"])
        listed = client.get("/connections").json()["connections"][0]
        self.assertIn("rate-limiting", listed["last_error"])
        # recovery clears the error
        self.fake.list_items = make_fake_adapter().list_items
        connsync.run_import(row["id"])
        listed = client.get("/connections").json()["connections"][0]
        self.assertIsNone(listed["last_error"])
        self.assertTrue(listed["last_sync"])

    def test_import_route_starts_job(self):
        row = self._connect_fake()
        r = client.post("/connections/import", json={"id": row["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        # daemon thread may still be running; poll the status route briefly
        import time
        for _ in range(50):
            job = client.get(f"/connections/import/status?id={row['id']}").json()["job"]
            if job and job.get("state") in ("done", "error"):
                break
            time.sleep(0.05)
        self.assertEqual(job["state"], "done", job)
        self.assertEqual(job["imported"], 2)


class TestErrorTaxonomy(ConnectionTestBase):
    def test_http_statuses_map_to_taxonomy(self):
        cases = [(401, connectors.ConnectorAuthError),
                 (403, connectors.ConnectorAccessError),
                 (429, connectors.ConnectorRateLimited),
                 (500, connectors.ConnectorUnavailable),
                 (418, connectors.ConnectorError)]
        import httpx

        for status, exc in cases:
            def handler(request, status=status):
                return httpx.Response(status)
            transport = httpx.MockTransport(handler)
            orig = httpx.request
            try:
                def fake_request(method, url, **kw):
                    with httpx.Client(transport=transport) as c:
                        return c.request(method, url)
                httpx.request = fake_request
                with self.assertRaises(exc):
                    connectors.request("GET", "https://vendor.test/x")
            finally:
                httpx.request = orig

    def test_test_route_maps_rate_limit_to_429(self):
        def limited(creds):
            raise connectors.ConnectorRateLimited("try again in a few minutes")
        self.fake.test = limited
        r = client.post("/connections/test", json={
            "service": "fakevendor", "credentials": {"api_key": "good-key"}})
        self.assertEqual(r.status_code, 429)


if __name__ == "__main__":
    unittest.main(verbosity=2)
