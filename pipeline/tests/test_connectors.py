"""UX-6 proof: watched-folder connectors + .eml extraction + erase-everything.

Watched folders are the local-first import surface: a directory on disk, polled,
new supported files ingested through the SAME path as a manual upload; the source
file is never modified (originals read-only, hard rule #5). .eml extraction is
stdlib-only. Erase-everything requires the typed phrase and refuses under an
active legal hold (never a spoliation machine).
"""

import sys
import tempfile
import time
import unittest
from email.message import EmailMessage
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import extractors  # noqa: E402
import ingest_worker  # noqa: E402
import routes_kb  # noqa: E402
import watchers  # noqa: E402
import api  # noqa: E402

client = TestClient(api.app)


class TestEmlExtraction(unittest.TestCase):
    def _eml(self, tmp, html=False):
        msg = EmailMessage()
        msg["From"] = "opposing@counsel.example"
        msg["To"] = "jake@firm.example"
        msg["Subject"] = "Settlement counteroffer"
        msg["Date"] = "Thu, 9 Jul 2026 10:00:00 -0500"
        if html:
            msg.add_alternative("<p>We propose <b>$45,000</b> to resolve.</p>",
                                subtype="html")
        else:
            msg.set_content("We propose $45,000 to resolve all claims.")
        p = tmp / "counteroffer.eml"
        p.write_bytes(msg.as_bytes())
        return p

    def test_plain_body_headers_single_page(self):
        tmp = Path(tempfile.mkdtemp())
        pages = extractors.extract(self._eml(tmp))
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["page_number"], 1)
        self.assertEqual(pages[0]["source"], "eml")
        for probe in ("Subject: Settlement counteroffer", "opposing@counsel.example",
                      "$45,000"):
            self.assertIn(probe, pages[0]["page_text"])

    def test_html_fallback_is_tag_stripped(self):
        tmp = Path(tempfile.mkdtemp())
        pages = extractors.extract(self._eml(tmp, html=True))
        self.assertIn("$45,000", pages[0]["page_text"])
        self.assertNotIn("<p>", pages[0]["page_text"])

    def test_eml_is_uploadable(self):
        self.assertIn(".eml", routes_kb._ALLOWED)


class TestWatchedFolders(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        self._docs, routes_kb.KB_DOCS = routes_kb.KB_DOCS, self.tmp / "kb"
        catalog.create_matter("Watch Matter")
        # record enqueues instead of running live ingest
        self._enq, ingest_worker.enqueue = ingest_worker.enqueue, \
            lambda *a, **k: self.enqueued.append(a) or 1
        self.enqueued = []
        watchers._seen_mtimes.clear()
        watchers._stats.clear()

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat
        routes_kb.KB_DOCS = self._docs
        ingest_worker.enqueue = self._enq
        watchers._seen_mtimes.clear()
        watchers._stats.clear()

    def test_validate_rejects_relative_missing_and_kb_tree(self):
        with self.assertRaises(ValueError):
            watchers.validate_folder("relative/path")
        with self.assertRaises(ValueError):
            watchers.validate_folder(self.tmp / "does-not-exist")
        inside = routes_kb.KB_DOCS / "watch-matter"
        inside.mkdir(parents=True)
        with self.assertRaises(ValueError):
            watchers.validate_folder(inside)

    def test_scan_picks_up_new_supported_stable_files_only(self):
        folder = self.tmp / "inbox"
        folder.mkdir()
        old = time.time() - 60
        (folder / "letter.txt").write_text("SYNTHETIC letter body")
        (folder / "notes.md").write_text("SYNTHETIC notes")
        (folder / "ignore.xyz").write_text("unsupported")
        (folder / ".hidden.txt").write_text("hidden")
        import os
        for f in folder.iterdir():
            os.utime(f, (old, old))
        (folder / "fresh.txt").write_text("still being written")  # too new -> skipped
        catalog.add_watch_folder("watch-matter", folder)

        queued = watchers.scan_once()
        names = sorted(d["filename"] for d in queued)
        self.assertEqual(names, ["letter.txt", "notes.md"])
        self.assertEqual(len(self.enqueued), 2)
        # source files untouched (originals read-only)
        self.assertEqual((folder / "letter.txt").read_text(), "SYNTHETIC letter body")
        # second pass: nothing new
        self.assertEqual(watchers.scan_once(), [])

    def test_rescan_of_changed_file_lands_touched_identical_does_not(self):
        # Council 2026-07-11 Move 4, Elena's filing hazard: a CORRECTED re-scan
        # of contract.txt (same name, newer mtime, new bytes) must be ingested;
        # a merely-touched identical file must not mint a duplicate row.
        # _STABLE_SECONDS is zeroed so "newer than the doc row" mtimes (which
        # are necessarily near-now) are not mistaken for still-being-written.
        import os
        from unittest import mock
        folder = self.tmp / "scans"
        folder.mkdir()
        f = folder / "contract.txt"
        f.write_text("SYNTHETIC v1 scan")
        os.utime(f, (time.time() - 60, time.time() - 60))
        catalog.add_watch_folder("watch-matter", folder)
        with mock.patch.object(watchers, "_STABLE_SECONDS", 0):
            self.assertEqual(len(watchers.scan_once()), 1)
            time.sleep(1.1)   # the doc row's updated stamp has 1s precision

            # touched but identical -> read again, dropped by checksum identity
            os.utime(f, None)
            self.assertEqual(watchers.scan_once(), [])
            self.assertEqual(len(catalog.list_documents("watch-matter")), 1)

            # corrected content, newer mtime -> re-ingested (suffixed name)
            f.write_text("SYNTHETIC v2 corrected scan")
            queued = watchers.scan_once()
        self.assertEqual(len(queued), 1, "corrected re-scan was silently dropped")
        names = sorted(d["filename"] for d in
                       catalog.list_documents("watch-matter"))
        self.assertEqual(names, ["contract-1.txt", "contract.txt"])

    def test_one_level_subfolders_are_scanned_deeper_are_not(self):
        # Council 2026-07-12: scanner trays write dated subfolders
        # (Scans/2026-07-12/x.pdf) — one level in, deeper deliberately not.
        import os
        folder = self.tmp / "tray"
        (folder / "2026-07-12").mkdir(parents=True)
        (folder / "2026-07-12" / "deep").mkdir()
        old = time.time() - 60
        top = folder / "top.txt"; top.write_text("SYNTHETIC top")
        sub = folder / "2026-07-12" / "scan.txt"; sub.write_text("SYNTHETIC sub")
        deep = folder / "2026-07-12" / "deep" / "nope.txt"
        deep.write_text("SYNTHETIC deep")
        hidden_dir = folder / ".git"; hidden_dir.mkdir()
        hid = hidden_dir / "config.txt"; hid.write_text("SYNTHETIC hidden dir")
        for f in (top, sub, deep, hid):
            os.utime(f, (old, old))
        link = folder / "linked"
        link.symlink_to(self.tmp)          # symlinked dir: never followed
        catalog.add_watch_folder("watch-matter", folder)
        names = sorted(d["filename"] for d in watchers.scan_once())
        self.assertEqual(names, ["scan.txt", "top.txt"])   # deep/.git/link excluded
        # restart semantics: keys are in-memory only — after a restart every
        # file is re-read once and checksum identity drops the known ones
        watchers._seen_mtimes.clear()
        self.assertEqual(watchers.scan_once(), [])

    def test_same_filename_in_two_subfolders_both_land(self):
        import os
        folder = self.tmp / "tray2"
        (folder / "a").mkdir(parents=True); (folder / "b").mkdir()
        old = time.time() - 60
        fa = folder / "a" / "scan.txt"; fa.write_text("SYNTHETIC A")
        fb = folder / "b" / "scan.txt"; fb.write_text("SYNTHETIC B")
        for f in (fa, fb):
            os.utime(f, (old, old))
        catalog.add_watch_folder("watch-matter", folder)
        self.assertEqual(len(watchers.scan_once()), 2)     # distinct relpath keys
        # both LAND, neither clobbers: the suffix loop keeps A and B distinct
        self.assertEqual(sorted(d["filename"]
                                for d in catalog.list_documents("watch-matter")),
                         ["scan-1.txt", "scan.txt"])

    def test_heartbeat_stats_and_status_fields(self):
        folder = self.tmp / "beat"
        folder.mkdir()
        row = catalog.add_watch_folder("watch-matter", folder)
        listed = client.get("/connectors/folders").json()["folders"]
        me = [f for f in listed if f["id"] == row["id"]][0]
        self.assertIsNone(me["checked_s_ago"])          # honest before first scan
        self.assertTrue(me["matter_exists"])

        watchers.scan_once()
        me = [f for f in client.get("/connectors/folders").json()["folders"]
              if f["id"] == row["id"]][0]
        self.assertIsNotNone(me["checked_s_ago"])
        self.assertLessEqual(me["checked_s_ago"], 5)
        self.assertEqual(me["files_added"], 0)

    def test_unfiled_is_a_legal_lazily_created_target(self):
        folder = self.tmp / "tray"
        folder.mkdir()
        self.assertIsNone(catalog.get_matter("unfiled"))
        r = client.post("/connectors/folders",
                        json={"matter": "unfiled", "path": str(folder)})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNotNone(catalog.get_matter("unfiled"))

    def test_routes_add_list_remove(self):
        folder = self.tmp / "drops"
        folder.mkdir()
        r = client.post("/connectors/folders",
                        json={"matter": "watch-matter", "path": str(folder)})
        self.assertEqual(r.status_code, 200, r.text)
        fid = r.json()["id"]
        listed = client.get("/connectors/folders").json()["folders"]
        self.assertTrue(any(f["id"] == fid and f["exists"] for f in listed))
        # duplicate rejected
        r2 = client.post("/connectors/folders",
                         json={"matter": "watch-matter", "path": str(folder)})
        self.assertEqual(r2.status_code, 400)
        client.post("/connectors/folders/remove", json={"id": fid})
        listed = client.get("/connectors/folders").json()["folders"]
        self.assertFalse(any(f["id"] == fid for f in listed))


class TestEraseEverything(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        self._docs, routes_kb.KB_DOCS = routes_kb.KB_DOCS, self.tmp / "kb"
        self._kdb, routes_kb.KB_DB = routes_kb.KB_DB, self.tmp / ".lancedb_kb"

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat
        routes_kb.KB_DOCS = self._docs
        routes_kb.KB_DB = self._kdb

    def test_requires_exact_phrase(self):
        catalog.create_matter("Erase Me")
        for bad in ("", "erase everything", "ERASE", "yes"):
            r = client.post("/data/erase", json={"confirm": bad})
            self.assertEqual(r.status_code, 400, bad)
        self.assertTrue(catalog.list_matters())    # nothing happened

    def test_refuses_under_active_hold(self):
        catalog.create_matter("Held Matter")
        catalog.place_hold("held-matter", "pending litigation")
        r = client.post("/data/erase", json={"confirm": "ERASE EVERYTHING"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("held-matter", r.json()["detail"])
        self.assertTrue(catalog.get_matter("held-matter"))    # untouched

    def test_erases_matters_and_profile(self):
        catalog.create_matter("Gone One")
        catalog.create_matter("Gone Two")
        catalog.set_profile({"name": "Jake", "memory_notes": ["prefers brevity"]})
        r = client.post("/data/erase", json={"confirm": "ERASE EVERYTHING"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(sorted(r.json()["matters_disposed"]),
                         ["gone-one", "gone-two"])
        self.assertEqual(catalog.list_matters(), [])
        self.assertNotIn("name", catalog.get_profile())


class TestMemoryFencing(unittest.TestCase):
    def test_answer_path_cannot_see_profile_or_memory(self):
        """Teachable memory feeds greeting/suggestions ONLY. The grounded answer
        path (answering.py + verifier.py) must have no route to the profile store —
        a remembered 'fact' must never contaminate a cited answer or cross matters."""
        import inspect
        import answering
        import verifier
        for mod in (answering, verifier):
            src = inspect.getsource(mod)
            for token in ("get_profile", "memory_notes", "import catalog",
                          "routes_profile"):
                self.assertNotIn(token, src,
                                 f"{mod.__name__} references {token} — memory fence broken")


if __name__ == "__main__":
    unittest.main(verbosity=2)
