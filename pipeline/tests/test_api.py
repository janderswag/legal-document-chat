"""M2-7 proof: thin FastAPI loopback HTTP surface over answer() (D-41, D-13).

The HTTP layer is a pass-through: POST /answer returns exactly what answer() returns
(chunk-derived citations D-38 + mechanically-verified spans D-19 + rejected_claims),
never re-introducing a model-asserted page. Safety is structural: binds 127.0.0.1
only (D-4), exposes only /health + /answer (no action route, D-2), and the answering
path makes only the loopback Ollama call (no non-loopback egress).
"""

import json
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PIPELINE_DIR.parent
MANIFEST = REPO_ROOT / "eval" / "golden_manifest.jsonl"
QUESTIONS = REPO_ROOT / "eval" / "golden_questions.jsonl"

sys.path.insert(0, str(PIPELINE_DIR))
import api  # noqa: E402  (the module under test)
from answering import answer, REFUSAL  # noqa: E402

PEMBERTON = "Pemberton Logistics (Nimbus MSA)"

client = TestClient(api.app)


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _fact(fid):
    return next(r for r in _read_jsonl(MANIFEST) if r["fact_id"] == fid)


def _q(fid):
    return next(r["question"] for r in _read_jsonl(QUESTIONS) if r["fact_id"] == fid)


class TestHealth(unittest.TestCase):
    def test_health_is_liveness_only_no_document_data(self):
        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok"})


class TestAnswerPresentFact(unittest.TestCase):
    def test_present_fact_returns_chunk_derived_verified_citation(self):
        f = _fact("F-004")
        r = client.post("/answer", json={"question": _q("F-004"), "matter": PEMBERTON})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("answer_text", body)
        self.assertEqual(body["rejected_claims"], [])
        # A chunk-derived, span-verified citation: REAL integer page (not model-asserted),
        # correct filename, with the page offsets the verifier produced.
        self.assertTrue(
            any(c["filename"] == f["filename"] and isinstance(c["page"], int)
                and c["page"] == f["page_number"] and "char_start" in c and "char_end" in c
                for c in body["citations"]),
            f"no chunk-derived verified citation: {body['citations']}",
        )


class TestAnswerNotFoundRefuses(unittest.TestCase):
    def test_not_found_refuses_with_no_asserted_citation(self):
        r = client.post("/answer", json={"question": _q("NF-001"), "matter": None})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn(REFUSAL, body["answer_text"])
        self.assertEqual(body["citations"], [])


class TestApiIsThinPassThrough(unittest.TestCase):
    def test_response_equals_direct_answer_call_verbatim(self):
        # Capture the real answer() once, then prove the route returns it byte-for-byte
        # (no field added/dropped, no model-asserted page injected by the HTTP layer).
        direct = answer(_q("F-001"), matter=PEMBERTON)
        orig = api.answer
        api.answer = lambda question, matter=None: direct
        try:
            r = client.post("/answer", json={"question": _q("F-001"), "matter": PEMBERTON})
        finally:
            api.answer = orig
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), direct)


class TestUnknownMatterRejected(unittest.TestCase):
    def test_unknown_matter_returns_400_not_injection(self):
        r = client.post("/answer", json={"question": "anything",
                                         "matter": "Robert'); DROP TABLE--"})
        self.assertEqual(r.status_code, 400)


class TestSafetyStructural(unittest.TestCase):
    def test_only_expected_readonly_routes_exist(self):
        # /answer is the sole POST (read-only retrieve+answer); the rest are read-only
        # GETs (health + the SC-5 demo surface: page, matter list, source PDF viewer).
        paths = {getattr(r, "path", None) for r in api.app.routes}
        app_paths = {p for p in paths if p and not p.startswith(("/openapi", "/docs", "/redoc"))}
        self.assertEqual(app_paths,
                         {"/", "/app", "/static/{asset:path}", "/health", "/answer",
                          "/matters", "/eval/matters", "/source/{filename:path}",
                          "/kb/upload", "/kb/documents", "/kb/source/{doc_id}",
                          "/kb/documents/{doc_id}",
                          # /kb/ingest/status (Move 0c): read-only ingest-queue progress
                          # for the Hub; no document content.
                          "/kb/ingest/status",
                          "/chat", "/chat/stream", "/chat/threads", "/chat/threads/{thread_id}",
                          "/kb/thumb/{doc_id}", "/kb/highlight/{doc_id}",
                          "/clauses/taxonomy", "/clauses/review",
                          "/grid",
                          "/setup", "/setup/status",
                          # /setup/pull (P1.5): setup-time model install via the LOCAL
                          # Ollama, allowlisted to the two pinned models — the one
                          # deliberate non-read-only setup action; no document data.
                          "/setup/pull",
                          "/settings/status"})

    def test_only_the_locked_kb_delete_mutates(self):
        # No PUT/PATCH anywhere; DELETE is exposed ONLY on the structurally-locked KB
        # remove route (hard rule #5 — remove-from-KB only, never an outside path).
        for r in api.app.routes:
            methods = getattr(r, "methods", None) or set()
            self.assertEqual(methods & {"PUT", "PATCH"}, set())
            if "DELETE" in methods:
                self.assertEqual(getattr(r, "path", ""), "/kb/documents/{doc_id}")

    def test_app_binds_loopback_only(self):
        self.assertEqual(api.HOST, "127.0.0.1")
        self.assertNotEqual(api.HOST, "0.0.0.0")

    def test_no_openapi_schema_surface(self):
        # B2 defense-in-depth: docs/redoc AND the OpenAPI schema are all disabled.
        for path in ("/openapi.json", "/docs", "/redoc"):
            self.assertEqual(client.get(path).status_code, 404, path)


class TestLoopbackOnlyEgress(unittest.TestCase):
    def test_answer_endpoint_only_connects_loopback(self):
        import socket
        original = socket.socket.connect
        seen = []

        def recording_connect(self, address, *a, **k):
            seen.append(address)
            return original(self, address, *a, **k)

        socket.socket.connect = recording_connect
        try:
            client.post("/answer", json={"question": _q("F-001"), "matter": PEMBERTON})
        finally:
            socket.socket.connect = original
        for addr in seen:
            host = addr[0] if isinstance(addr, tuple) else str(addr)
            self.assertIn(host, ("127.0.0.1", "::1", "localhost"), f"non-loopback egress: {addr}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
