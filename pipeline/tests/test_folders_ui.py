"""Council 2026-07-11 Move 4 — watched folders the attorney can understand.

Native folder picker via the pywebview bridge (text input survives as the
no-bridge fallback), split guards that name the field they blame, a heartbeat
row that reads as alive, subfolder honesty in the copy, and the entry point on
the matter detail page. Static assertions on served JS + the launcher source,
matching the repo idiom."""

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import api  # noqa: E402

client = TestClient(api.app)
LAUNCHER_SRC = (PIPELINE_DIR.parent / "desktop" / "launcher.py").read_text()


class TestFoldersUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = client.get("/static/app.js").text

    def test_native_picker_with_fallback(self):
        self.assertIn("pywebview.api.choose_folder", self.js)
        self.assertIn("folder-choose", self.js)
        self.assertIn("Choose a folder", self.js)
        # the text input survives for dev/browser (no bridge)
        self.assertIn("folder-path", self.js)

    def test_guards_are_split_and_name_their_field(self):
        # the old conflated guard blamed the matter even when it was chosen
        self.assertNotIn("Choose a matter and enter a folder path", self.js)
        self.assertIn("Choose which matter this folder feeds", self.js)
        self.assertIn("pick the folder to watch", self.js)

    def test_heartbeat_row_strings(self):
        self.assertIn("checked ", self.js)
        self.assertIn("folder missing", self.js)
        self.assertIn("matter removed", self.js)
        self.assertIn("startFolderHeartbeat", self.js)

    def test_subfolder_honesty_copy(self):
        # B3 (council 2026-07-12): one level in — the copy must state both what
        # now works (a scanner's dated folders) and the boundary (no deeper)
        self.assertIn("immediate subfolders are watched", self.js)
        self.assertIn("deeper nesting is not imported", self.js)

    def test_matter_detail_entry_point(self):
        self.assertIn("matter-watch-folder", self.js)
        self.assertIn("Watch a folder for this matter", self.js)


class TestLauncherBridge(unittest.TestCase):
    def test_js_bridge_is_dialogs_only_and_wired(self):
        self.assertIn("class JsBridge", LAUNCHER_SRC)
        self.assertIn("FOLDER_DIALOG", LAUNCHER_SRC)
        self.assertIn("js_api=bridge", LAUNCHER_SRC)
        # bridge exposes exactly one method: the folder dialog (no file IO)
        bridge = LAUNCHER_SRC[LAUNCHER_SRC.index("class JsBridge"):
                              LAUNCHER_SRC.index("bridge = JsBridge()")]
        defs = [ln.strip() for ln in bridge.splitlines()
                if ln.strip().startswith("def ")]
        self.assertEqual(defs, ["def __init__(self):", "def choose_folder(self):"])
        for forbidden in ("open(", "write", "unlink", "rmtree", "remove("):
            self.assertNotIn(forbidden, bridge)
        # pywebview exposes every PUBLIC attribute of the js_api object
        # RECURSIVELY — a public self.window would hand page JS the whole
        # Window API (load_url to a remote origin, SAVE dialogs, destroy).
        self.assertIn("self._window", bridge)
        self.assertNotIn("self.window", bridge)
        self.assertIn("bridge._window = window", LAUNCHER_SRC)
        self.assertNotIn("bridge.window = window", LAUNCHER_SRC)


if __name__ == "__main__":
    unittest.main(verbosity=2)
