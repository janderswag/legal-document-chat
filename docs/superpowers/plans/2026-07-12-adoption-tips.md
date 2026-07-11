# Adoption Tips Implementation Plan (the council's three "tips my yes" items)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the three items the 2026-07-11 adoption-verdict council said tip the most yeses: (1) kill the false "Potentially missing" signal (interim label demotion now, per-document retrieval scoping in the next engine cycle), (2) make scanned paper work out of the box (bundle Tesseract + one-level subfolder recursion), (3) refuse-with-explanation on under-16GB machines.

**Architecture:** Two releases. **v0.5.1** (Workstreams A-C) touches zero engine code — UI copy, packaging, watchers, launcher — and ships through targeted tests + the packaged smoke gate. **v0.6.0** (Workstream D) is the engine-gated cycle: `retrieve()` gains a validated `source_filename` hard pre-filter, threaded through `answer()` into single-document reviews, a grid negative-cell verification pass, and a matter-checklist absence-verification pass; it ships only through the FULL golden gate (63/63 + 9/9 + 0 rejected must stay identical for unscoped calls) plus a new targeted scope-proof test class.

**Tech Stack:** Existing only — FastAPI, LanceDB, pytesseract (wrapper already a dep; the BINARY is what's missing), pywebview, PyInstaller. One new BUILD-machine-only tool: `dylibbundler` (Homebrew) for vendoring Tesseract's dylibs. No new runtime Python dependencies.

## Global Constraints

- The answer engine (`answering.py`, `retrieval.py`, `verifier.py`) is frozen: Workstreams A-C must have ZERO diffs there; Workstream D changes `retrieval.py`/`answering.py` and therefore requires the full 63/63 + 9/9 + 0-rejected golden gate, run in `~/projects/legal-doc-intelligence` (`PATH="$PWD/pipeline/.venv/bin:$PATH"`, `run_golden.py <tag>` then `score_golden.py`).
- Never a fabricated citation; a clause is "found" ONLY with a span-verified, chunk-derived citation (D-19/D-38). docuchat never computes a deadline date.
- No em-dashes in any user-facing copy. No AI-slop patterns (Jonas's blacklist is canon).
- Adversarial review after every task (five-for-five last session; keep it). Packaged smoke gate (`desktop/smoke_packaged.sh`) mandatory before either release; never `SKIP_SMOKE`.
- Tests are `unittest`, run as `cd pipeline && .venv/bin/python -m unittest tests.<module>`. Dev clone has ~45 known eval-data failures — compare against that baseline, never blame new work for them.
- Build recipe: eval repo, `PATH` includes `pipeline/.venv/bin`, `APPLE_DEV_ID_APP='Developer ID Application: Jake Anderson (8W2KYM5Y4J)' NOTARY_PROFILE=docuchat-notary BUNDLE_OLLAMA=1 ./desktop/build_macos.sh`; check `$?` unpiped.
- pywebview exposes public js_api attributes recursively — anything on a bridge object stays underscore-private.

---

## Workstream A — Interim label demotion (v0.5.1, no engine)

### Task A1: Retrieval-honest "not located" language everywhere

**Files:**
- Modify: `pipeline/static/app.js` (CLAUSE_STATUS ~line 2450; GRID_BADGE cell text ~2540; CLAUSE_STATUS_TEXT export labels ~2760)
- Modify: `pipeline/routes_clauses.py` (`status_label` dict in `review_docx`, ~line 118)
- Modify: `pipeline/static/app.css` (`.clause-badge.missing`, `.clause-row.missing`)
- Test: `pipeline/tests/test_clauses_ui.py`, `pipeline/tests/test_review_docx.py`

**Interfaces:**
- Consumes: the `potentially_missing` status value (UNCHANGED — it is API/persisted-run vocabulary; only display strings change).
- Produces: display label `"Not located in the passages checked"`; export label `"Not located (passages checked, not a page-by-page read)"`. Later tasks (D5) upgrade these to `"Not located in <filename> (every passage checked)"` when a scoped verification ran.

- [ ] **Step 1: Write the failing tests**

```python
# append to pipeline/tests/test_clauses_ui.py
class TestRetrievalHonestLabels(unittest.TestCase):
    """Adoption council 2026-07-11: 'Potentially missing' reads as a legal
    conclusion the retrieval cannot support. The label must say what the
    system actually did: it checked the most relevant passages and did not
    locate the clause."""

    @classmethod
    def setUpClass(cls):
        cls.js = client.get("/static/app.js").text
        cls.css = client.get("/static/app.css").text

    def test_display_label_is_retrieval_honest(self):
        self.assertIn("Not located in the passages checked", self.js)
        self.assertNotIn('label: "Potentially missing"', self.js)

    def test_status_value_unchanged_for_persisted_runs(self):
        # persisted v0.5.0 runs must still render: the STATUS KEY survives
        self.assertIn("potentially_missing", self.js)

    def test_badge_is_demoted_from_warning_amber(self):
        # Jonas: a maybe-absence must not shout like a confirmed problem
        i = self.css.index(".clause-badge.missing{")
        seg = self.css[i:i + 120]
        self.assertNotIn("--warn", seg)
        self.assertIn("--muted", seg)
```

```python
# in pipeline/tests/test_review_docx.py, REPLACE the two assertions that pin
# the old label inside test_caveat_and_statuses_present:
#   self.assertIn("Potentially missing", statuses)
# with:
        self.assertIn("Not located (passages checked, not a page-by-page read)",
                      statuses)
# and in test_red_flags_sort_first_and_cite_present keep the sort assertion
# (arbitration still leads) — only the label text changes.
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd ~/legal-document-chat/pipeline && .venv/bin/python -m unittest tests.test_clauses_ui.TestRetrievalHonestLabels tests.test_review_docx -v`
Expected: FAIL (old labels present, amber badge present)

- [ ] **Step 3: Apply the copy + style changes**

```js
// app.js — CLAUSE_STATUS (Contract Review rows)
var CLAUSE_STATUS = {
  found: { label: "Found", cls: "found" },
  potentially_missing: { label: "Not located in the passages checked", cls: "missing" },
  not_confirmed: { label: "Not confirmed", cls: "unconfirmed" },
};
// grid cell text: replace " <span class='muted'>not located</span>" branch label
// (keep as-is — already honest) and CLAUSE_STATUS_TEXT for exports:
var CLAUSE_STATUS_TEXT = {
  found: "Found (span-verified)",
  potentially_missing: "Not located (passages checked, not a page-by-page read)",
  not_confirmed: "Not confirmed (spans rejected)",
};
```

```python
# routes_clauses.py review_docx status_label
status_label = {"found": "Found (span-verified)",
                "potentially_missing":
                    "Not located (passages checked, not a page-by-page read)",
                "not_confirmed": "Not confirmed (spans rejected)"}
```

```css
/* app.css — demote from warn-amber to muted; row keeps a visible left edge */
.clause-badge.missing{background:var(--panel-2);color:var(--muted)}
.clause-row.missing{border-left-color:var(--border-2)}
```

Also update the two summary-chip strings in `app.js` (`reviewTallyHtml` and the old
`clause-summary` builder) from `" potentially missing"` to `" not located"`.

- [ ] **Step 4: Run the UI + docx + palette batch**

Run: `.venv/bin/python -m unittest tests.test_clauses_ui tests.test_review_docx tests.test_grid_ui tests.test_digest_ui -v`
Expected: PASS. Also `node --check pipeline/static/app.js`.

- [ ] **Step 5: Adversarial review, then commit**

```bash
git add pipeline/static/app.js pipeline/static/app.css pipeline/routes_clauses.py pipeline/tests/
git commit -m "fix(review): retrieval-honest 'Not located' language, badge demoted (council interim)"
```

---

## Workstream B — Scanned paper works out of the box (v0.5.1, no engine)

### Task B1: Vendor the Tesseract binary + tessdata into the build

**Why:** `ingestion.py:91` calls `pytesseract`, which SHELLS OUT to a system
`tesseract` binary. The spec bundles the Python wrapper only — on any Mac
without Homebrew Tesseract, every scanned page silently fails OCR.

**Files:**
- Create: `desktop/vendor_tesseract.sh`
- Modify: `desktop/build_macos.sh` (call the vendor script before `pyinstaller`, same pattern as the Ollama vendor block at line ~25)
- Modify: `desktop/build_macos.spec` (add the vendored tree to `datas`)
- Test: `pipeline/tests/test_deploy_scripts.py` (static assertions)

**Interfaces:**
- Produces: `vendor/tesseract/bin/tesseract`, `vendor/tesseract/lib/*.dylib`, `vendor/tesseract/share/tessdata/eng.traineddata` in the repo build tree; inside the bundle at `Contents/Resources/vendor/tesseract/...` (PyInstaller `datas` target `vendor/tesseract`).

- [ ] **Step 1: Write the vendor script**

```bash
#!/usr/bin/env bash
# desktop/vendor_tesseract.sh — copy the build machine's Tesseract into
# vendor/tesseract with RELOCATABLE dylibs (@executable_path), so the packaged
# app OCRs scanned PDFs with zero user installs. Build-machine prerequisites:
#   brew install tesseract dylibbundler
# Idempotent: skips if vendor/tesseract/bin/tesseract already exists.
set -euo pipefail
cd "$(dirname "$0")/.."
VENDOR="vendor/tesseract"
[[ -x "$VENDOR/bin/tesseract" ]] && { echo "==> tesseract already vendored"; exit 0; }
TES="$(command -v tesseract || true)"
[[ -n "$TES" ]] || { echo "ERROR: brew install tesseract first" >&2; exit 1; }
command -v dylibbundler >/dev/null || { echo "ERROR: brew install dylibbundler" >&2; exit 1; }
mkdir -p "$VENDOR/bin" "$VENDOR/lib" "$VENDOR/share/tessdata"
cp "$TES" "$VENDOR/bin/tesseract"
chmod u+w "$VENDOR/bin/tesseract"
# rewrite every non-system dylib reference to @executable_path/../lib
dylibbundler -of -b -x "$VENDOR/bin/tesseract" -d "$VENDOR/lib" -p '@executable_path/../lib'
TESSDATA="$(brew --prefix tesseract)/share/tessdata"
cp "$TESSDATA/eng.traineddata" "$VENDOR/share/tessdata/"
cp "$TESSDATA/osd.traineddata" "$VENDOR/share/tessdata/" 2>/dev/null || true
"$VENDOR/bin/tesseract" --version >/dev/null || { echo "ERROR: vendored binary broken" >&2; exit 1; }
echo "==> vendored tesseract $("$VENDOR/bin/tesseract" --version 2>&1 | head -1)"
```

- [ ] **Step 2: Wire into the build**

```bash
# build_macos.sh, immediately after the Ollama vendor block:
echo "==> Vendoring Tesseract (scanned-PDF OCR)..."
./desktop/vendor_tesseract.sh
```

```python
# build_macos.spec, in datas (alongside the existing entries):
("../vendor/tesseract", "vendor/tesseract"),
```

- [ ] **Step 3: Static test**

```python
# append to pipeline/tests/test_deploy_scripts.py
class TestTesseractVendored(unittest.TestCase):
    def test_build_vendors_tesseract(self):
        sh = (ROOT / "desktop" / "build_macos.sh").read_text()
        self.assertIn("vendor_tesseract.sh", sh)
        spec = (ROOT / "desktop" / "build_macos.spec").read_text()
        self.assertIn("vendor/tesseract", spec)
        vend = (ROOT / "desktop" / "vendor_tesseract.sh").read_text()
        self.assertIn("eng.traineddata", vend)
        self.assertIn("@executable_path", vend)   # relocatable, not brew-pathed
```

Run: `.venv/bin/python -m unittest tests.test_deploy_scripts -v` — Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add desktop/vendor_tesseract.sh desktop/build_macos.sh desktop/build_macos.spec pipeline/tests/test_deploy_scripts.py
git commit -m "build(ocr): vendor tesseract binary + tessdata into the bundle"
```

### Task B2: Point pytesseract at the bundled binary in frozen builds

**Files:**
- Modify: `pipeline/ingestion.py` (top of the OCR section, before the `import pytesseract` use at line ~91)
- Test: `pipeline/tests/test_ocr_bundle.py` (create)

**Interfaces:**
- Produces: `ingestion.configure_tesseract()` — idempotent; returns the resolved
  tesseract command string ("system default" when unfrozen/absent). Called once
  at module import.

- [ ] **Step 1: Failing test**

```python
# pipeline/tests/test_ocr_bundle.py
"""Frozen builds must OCR with the VENDORED tesseract (Contents/Resources/
vendor/tesseract), never assume a Homebrew install on the user's Mac."""
import sys, unittest
from pathlib import Path
from unittest import mock

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import ingestion  # noqa: E402


class TestConfigureTesseract(unittest.TestCase):
    def test_frozen_uses_vendored_binary_and_tessdata(self):
        fake_root = Path("/tmp/fake-bundle/Resources")
        with mock.patch.object(ingestion.apppaths, "assets_root",
                               return_value=fake_root), \
             mock.patch.object(ingestion.Path, "is_file", return_value=True), \
             mock.patch.dict(ingestion.os.environ, {}, clear=False):
            cmd = ingestion.configure_tesseract()
        self.assertEqual(cmd, str(fake_root / "vendor/tesseract/bin/tesseract"))
        self.assertEqual(ingestion.os.environ.get("TESSDATA_PREFIX"),
                         str(fake_root / "vendor/tesseract/share/tessdata"))

    def test_dev_without_vendor_leaves_system_default(self):
        with mock.patch.object(ingestion.Path, "is_file", return_value=False):
            self.assertEqual(ingestion.configure_tesseract(), "system default")
```

Run: `.venv/bin/python -m unittest tests.test_ocr_bundle -v` — Expected: FAIL (`configure_tesseract` not defined).

- [ ] **Step 2: Implement**

```python
# ingestion.py (module level, near the other imports; apppaths already imported
# elsewhere in the pipeline — add `import apppaths` + `import os` if absent)
def configure_tesseract():
    """Point pytesseract at the vendored binary when it exists (frozen app:
    Contents/Resources/vendor/tesseract). Dev machines keep the system
    tesseract. Idempotent; returns the resolved command for logging."""
    vend = apppaths.assets_root() / "vendor" / "tesseract"
    binary = vend / "bin" / "tesseract"
    if binary.is_file():
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = str(binary)
        os.environ["TESSDATA_PREFIX"] = str(vend / "share" / "tessdata")
        return str(binary)
    return "system default"


configure_tesseract()
```

- [ ] **Step 3: Run the OCR-adjacent batch**

Run: `.venv/bin/python -m unittest tests.test_ocr_bundle tests.test_ingestion -v`
Expected: test_ocr_bundle PASS; test_ingestion failures no worse than the known eval-data baseline.

- [ ] **Step 4: Extend the packaged smoke gate (step g)**

```bash
# desktop/smoke_packaged.sh, after step (e) review-SSE, before the version step:
# --- (f2) scanned-page OCR works in the bundle (vendored tesseract) ----------
# A 1-page image-only PDF (rendered glyphs, no text layer) is generated by
# desktop/make_smoke_scan.py (Step 5) with the BUILD machine's pipeline venv;
# if the vendored tesseract is missing or broken, extraction yields no text
# and the doc parks in needs_review/failed instead of ready.
scan_pdf="$SCRATCH_DIR/smoke_scan.pdf"
"pipeline/.venv/bin/python" desktop/make_smoke_scan.py "$scan_pdf"
up="$(curl -s -X POST "$BASE/kb/upload?matter=$matter_slug&filename=smoke_scan.pdf&doc_type=document" --data-binary "@$scan_pdf")"
sid="$(echo "$up" | jq -r '.id // empty')"
[[ -n "$sid" ]] || fail "scanned-pdf upload returned no id — body: $up"
deadline=$((SECONDS + UPLOAD_TIMEOUT)); sstat=""
while [[ $SECONDS -lt $deadline ]]; do
  sstat="$(curl -s "$BASE/kb/documents?matter=$matter_slug" | jq -r --arg id "$sid" '.documents[] | select((.id|tostring)==$id) | .status')"
  [[ "$sstat" == "ready" ]] && break
  sleep 1
done
[[ "$sstat" == "ready" ]] || fail "scanned PDF never reached ready (last: '$sstat') — vendored tesseract broken?"
echo "==> (f2) scanned-page OCR -> ready (vendored tesseract works in the bundle)"
```

- [ ] **Step 5: Write the scan generator used by the smoke step**

```python
# desktop/make_smoke_scan.py
"""Emit a 1-page IMAGE-ONLY PDF (rendered text, no text layer) for the smoke
gate's OCR step. Uses PyMuPDF only (already a pipeline dependency)."""
import sys
import fitz  # PyMuPDF

out = sys.argv[1]
doc = fitz.open()
page = doc.new_page(width=612, height=792)
page.insert_text((72, 200), "SYNTHETIC SCANNED SMOKE PAGE", fontsize=24)
page.insert_text((72, 260), "docuchat OCR gate. Not a real document.", fontsize=16)
pix = page.get_pixmap(dpi=200)          # rasterize: kills the text layer
img = fitz.open()
ip = img.new_page(width=612, height=792)
ip.insert_image(ip.rect, pixmap=pix)
img.save(out)
print(f"wrote {out}")
```

- [ ] **Step 6: Commit**

```bash
git add pipeline/ingestion.py pipeline/tests/test_ocr_bundle.py desktop/smoke_packaged.sh desktop/make_smoke_scan.py
git commit -m "feat(ocr): frozen builds use the vendored tesseract; smoke gate proves OCR in the bundle"
```

### Task B3: Watched folders recurse one level

**Files:**
- Modify: `pipeline/watchers.py` (`scan_once` entry iteration; `_seen_mtimes` key)
- Modify: `pipeline/static/app.js` (the folders panel copy: "Only the folder itself is watched" line)
- Test: `pipeline/tests/test_connectors.py` (`TestWatchedFolders`)

**Interfaces:**
- Consumes: `_seen_mtimes` map from v0.5.0 — key changes from `(folder_id, name)` to `(folder_id, relpath)`.
- Produces: files in immediate subfolders (`folder/*/file.pdf`) are picked up; deeper nesting is not, and the UI copy says exactly that.

- [ ] **Step 1: Failing test**

```python
# append inside TestWatchedFolders (test_connectors.py)
    def test_one_level_subfolders_are_scanned_deeper_are_not(self):
        # Council: scanner trays write dated subfolders (Scans/2026-07-12/x.pdf).
        import os
        folder = self.tmp / "tray"
        (folder / "2026-07-12").mkdir(parents=True)
        (folder / "2026-07-12" / "deep").mkdir()
        old = time.time() - 60
        top = folder / "top.txt"; top.write_text("SYNTHETIC top")
        sub = folder / "2026-07-12" / "scan.txt"; sub.write_text("SYNTHETIC sub")
        deep = folder / "2026-07-12" / "deep" / "nope.txt"; deep.write_text("SYNTHETIC deep")
        for f in (top, sub, deep):
            os.utime(f, (old, old))
        catalog.add_watch_folder("watch-matter", folder)
        names = sorted(d["filename"] for d in watchers.scan_once())
        self.assertEqual(names, ["scan.txt", "top.txt"])   # deep/ excluded

    def test_same_filename_in_two_subfolders_both_land(self):
        import os
        folder = self.tmp / "tray2"
        (folder / "a").mkdir(parents=True); (folder / "b").mkdir()
        old = time.time() - 60
        fa = folder / "a" / "scan.txt"; fa.write_text("SYNTHETIC A")
        fb = folder / "b" / "scan.txt"; fb.write_text("SYNTHETIC B")
        for f in (fa, fb): os.utime(f, (old, old))
        catalog.add_watch_folder("watch-matter", folder)
        self.assertEqual(len(watchers.scan_once()), 2)     # distinct relpath keys
```

Run: `.venv/bin/python -m unittest tests.test_connectors.TestWatchedFolders -v` — Expected: the two new tests FAIL.

- [ ] **Step 2: Implement**

```python
# watchers.py scan_once — replace the `entries = sorted(folder.iterdir())` block:
        try:
            entries = sorted(folder.iterdir())
            for sub in list(entries):
                # one level of subfolders (scanner trays write dated dirs);
                # deeper nesting is deliberately NOT walked, and the UI says so
                if sub.is_dir() and not sub.name.startswith("."):
                    try:
                        entries.extend(sorted(sub.iterdir()))
                    except OSError as e:
                        print(f"[watchers] cannot read {sub}: {e}", file=sys.stderr)
        except OSError as e:
            ...
# and key by path relative to the watched root (subfolder twins stay distinct):
            key = (wf["id"], str(f.relative_to(folder)))
```

```js
// app.js folders panel copy:
"Only the folder and its immediate subfolders are watched (one level - a " +
"scanner's dated folders work; deeper nesting does not). " +
```

- [ ] **Step 3: Run the batch, adversarial review, commit**

Run: `.venv/bin/python -m unittest tests.test_connectors tests.test_folders_ui -v` — Expected: PASS.

```bash
git add pipeline/watchers.py pipeline/static/app.js pipeline/tests/test_connectors.py pipeline/tests/test_folders_ui.py
git commit -m "feat(folders): one-level subfolder recursion (scanner trays), relpath-keyed rescan"
```

---

## Workstream C — RAM gate (v0.5.1, no engine)

### Task C1: Refuse-with-explanation under 16GB

**Files:**
- Modify: `desktop/launcher.py` (preflight in `main()` before window creation; `LOWRAM_HTML` next to `FAIL_HTML`/`SPLASH_HTML`)
- Modify: `site/index.html` (system requirements line near the download button)
- Test: `pipeline/tests/test_launcher.py`

**Interfaces:**
- Produces: `launcher.total_ram_bytes()` (int; `sysctl -n hw.memsize` on macOS, 0 on failure = never blocks), `launcher.MIN_RAM_BYTES = 16 * 1024**3`, `launcher.ram_ok()` (bool; True when detection fails — fail OPEN, never strand a capable machine on a sysctl quirk). `DOCUCHAT_SKIP_RAM_GATE=1` escape hatch (documented in the dialog itself).

- [ ] **Step 1: Failing tests**

```python
# append to pipeline/tests/test_launcher.py
class TestRamGate(unittest.TestCase):
    """Adoption council: an 8GB Mac degrades mysteriously (Ollama swap-thrash);
    the launcher must refuse WITH AN EXPLANATION instead. Fails OPEN: if RAM
    cannot be read, the gate never blocks."""

    def test_threshold_logic(self):
        with mock.patch.object(launcher, "total_ram_bytes", return_value=8 * 1024**3):
            self.assertFalse(launcher.ram_ok())
        with mock.patch.object(launcher, "total_ram_bytes", return_value=16 * 1024**3):
            self.assertTrue(launcher.ram_ok())

    def test_detection_failure_fails_open(self):
        with mock.patch.object(launcher, "total_ram_bytes", return_value=0):
            self.assertTrue(launcher.ram_ok())

    def test_escape_hatch(self):
        with mock.patch.object(launcher, "total_ram_bytes", return_value=8 * 1024**3), \
             mock.patch.dict(launcher.os.environ, {"DOCUCHAT_SKIP_RAM_GATE": "1"}):
            self.assertTrue(launcher.ram_ok())

    def test_lowram_html_explains_and_names_the_requirement(self):
        self.assertIn("16 GB", launcher.LOWRAM_HTML)
        self.assertIn("on this Mac", launcher.LOWRAM_HTML)   # local-model framing
```

Run: `.venv/bin/python -m unittest tests.test_launcher.TestRamGate -v` — Expected: FAIL.

- [ ] **Step 2: Implement**

```python
# launcher.py, near the other preflight helpers:
MIN_RAM_BYTES = 16 * 1024**3


def total_ram_bytes():
    """Physical RAM; 0 when undeterminable (the gate then fails open)."""
    try:
        out = subprocess.run(["sysctl", "-n", "hw.memsize"],
                             capture_output=True, text=True, timeout=5)
        return int(out.stdout.strip() or 0)
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return 0


def ram_ok():
    if os.environ.get("DOCUCHAT_SKIP_RAM_GATE") == "1":
        return True
    total = total_ram_bytes()
    return total == 0 or total >= MIN_RAM_BYTES


LOWRAM_HTML = """<!doctype html><html><body style="font-family:-apple-system;
background:#f4f0e8;color:#1d1b16;display:flex;align-items:center;justify-content:center;
height:100vh;margin:0"><div style="max-width:480px;padding:32px">
<h2 style="margin:0 0 12px">This Mac does not have enough memory for docuchat</h2>
<p>docuchat runs its AI models entirely on this Mac - that is what keeps your
documents private - and the models need <b>16 GB of memory</b>. This Mac has
{ram_gb} GB, so answers would be extremely slow or fail outright.</p>
<p style="color:#6b6557;font-size:14px">Nothing was installed or changed. If you
believe this detection is wrong, relaunch from Terminal with
<code>DOCUCHAT_SKIP_RAM_GATE=1 open -a docuchat</code>.</p>
</div></body></html>"""
```

```python
# in main(), immediately after the DOCUCHAT_SMOKE early-return (the smoke path
# must NEVER be gated) and BEFORE any server/Ollama start:
    if not ram_ok():
        import webview
        gb = round(total_ram_bytes() / 1024**3)
        w = webview.create_window("docuchat", html=LOWRAM_HTML.replace("{ram_gb}", str(gb)),
                                  width=640, height=420)
        webview.start()
        return 0
```

```html
<!-- site/index.html, next to the download button -->
<p class="muted">Requires an Apple silicon Mac with 16 GB of memory. Your documents never leave it.</p>
```

- [ ] **Step 3: Run tests, adversarial review, commit**

Run: `.venv/bin/python -m unittest tests.test_launcher tests.test_deploy_scripts -v` — Expected: PASS.

```bash
git add desktop/launcher.py site/index.html pipeline/tests/test_launcher.py
git commit -m "feat(launcher): 16GB RAM gate - refuse with an explanation, fail open, escape hatch"
```

### Task C2: Ship v0.5.1

- [ ] Bump `pipeline/appversion.py` + `site/index.html` softwareVersion to `0.5.1` (spec imports APP_VERSION); run `tests.test_deploy_scripts`.
- [ ] Full dev suite: compare against the 45-known-failure baseline; zero new failures.
- [ ] Eval repo: pull, `PATH="$PWD/pipeline/.venv/bin:$PATH" APPLE_DEV_ID_APP='Developer ID Application: Jake Anderson (8W2KYM5Y4J)' NOTARY_PROFILE=docuchat-notary BUNDLE_OLLAMA=1 ./desktop/build_macos.sh`; check `$?` unpiped. Smoke now has the OCR step — it must PASS.
- [ ] NO golden gate needed (engine untouched) — but verify `git diff v0.5.0..HEAD -- pipeline/answering.py pipeline/retrieval.py pipeline/verifier.py` is empty before claiming that.
- [ ] Draft GitHub release with DMG; owner click-through (manual items: folder picker still works; a real scanned page OCRs); owner publishes.

---

## Workstream D — Per-document retrieval scoping (v0.6.0, THE engine cycle)

**Design (read before implementing).** Root cause of false "not located": every
clause/grid call retrieves matter-wide top-5; in a 6+ document matter the top-5
saturates with other documents' chunks, so a clause present in document X never
surfaces. The fix is a validated `source_filename` hard pre-filter in
`retrieve()` (same pattern as the D-35 matter filter), used three ways:
1. **Single-document review** (`doc_id` set): retrieval scoped to that file. Direct, same call count.
2. **Grid cells**: keep the memoized matter-wide pass (cheap, correct for FOUND), then re-ask ONLY the negative cells (`potentially_missing` / `not_confirmed`) scoped to their document. Cost: one extra call per negative cell, streamed as `cell-verify` events.
3. **Matter checklist**: after the streamed pass, for each `potentially_missing` row run scoped re-asks per candidate document (respecting the attorney-declared doc-type filter) until found or exhausted; emit `verify` events; row upgrades to `found` (with span-verified citation) or to verified-absence display "Not located in <N> documents (every document checked individually)".
Unscoped calls are byte-identical (default `source_filename=None`), so the 63/63
golden gate MUST score identical; a new targeted class (G-SCOPE) proves the
scoped behavior. Batch the other engine items (answering timeouts, M-1 query
rewriting) into this cycle ONLY if the council re-confirms; this plan ships
scoping alone rather than risking the batch.

### Task D1: `retrieve(..., source_filename=)` hard pre-filter

**Files:**
- Modify: `pipeline/retrieval.py` (`_matter_filter` gains a sibling; `retrieve()` signature)
- Test: `pipeline/tests/test_retrieval_scope.py` (create; runs against a temp store like `test_search_routes` — NOT the eval store, so it runs in the dev clone)

**Interfaces:**
- Produces: `retrieve(question, matter=None, top_k=5, db_path=None, rerank=False, candidate_k=20, hybrid=False, fts_query=None, source_filename=None)`. `source_filename` requires `matter` (scope inside a matter only), is validated against the store's filenames for that matter (unknown -> `ValueError`), and is escaped exactly like the matter filter (`chr(39)` doubling).

- [ ] **Step 1: Failing tests**

```python
# pipeline/tests/test_retrieval_scope.py
"""G-SCOPE unit layer: source_filename is a HARD pre-filter (D-18 style) —
scoped retrieval returns only that document's chunks, unknown filenames are
rejected, scoping without a matter is rejected, and default None is the
byte-identical unscoped path."""
import sys, tempfile, time, unittest
from pathlib import Path
from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog, routes_kb, api  # noqa: E402
import retrieval  # noqa: E402

client = TestClient(api.app)


class TestSourceFilenameScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, cls.tmp / "cat.db"
        cls._db, routes_kb.KB_DB = routes_kb.KB_DB, cls.tmp / ".lancedb_kb"
        cls._docs, routes_kb.KB_DOCS = routes_kb.KB_DOCS, cls.tmp / "kb"
        catalog.create_matter("Scope Matter")
        # indemnification lives ONLY in b.txt; a.txt..e.txt flood the matter
        for name, body in [("a.txt", "SYNTHETIC. Payment terms net thirty days. " * 30),
                           ("b.txt", "SYNTHETIC. Each party shall indemnify the other "
                                     "against third-party claims arising from breach."),
                           ("c.txt", "SYNTHETIC. Governing law is Delaware. " * 30),
                           ("d.txt", "SYNTHETIC. Termination on sixty days notice. " * 30),
                           ("e.txt", "SYNTHETIC. Confidentiality survives five years. " * 30)]:
            client.post(f"/kb/upload?matter=scope-matter&filename={name}",
                        content=body.encode())
        deadline = time.time() + 180
        while time.time() < deadline:
            rows = client.get("/kb/documents?matter=scope-matter").json()["documents"]
            if rows and all(d["status"] == "ready" for d in rows):
                break
            time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        catalog.DEFAULT_DB = cls._cat
        routes_kb.KB_DB = cls._db
        routes_kb.KB_DOCS = cls._docs

    def test_scoped_returns_only_that_documents_chunks(self):
        rows = retrieval.retrieve("indemnification obligations", matter="scope-matter",
                                  db_path=str(routes_kb.KB_DB), source_filename="b.txt")
        self.assertTrue(rows)
        self.assertTrue(all(r["source_filename"] == "b.txt" for r in rows))

    def test_unknown_filename_rejected(self):
        with self.assertRaises(ValueError):
            retrieval.retrieve("anything", matter="scope-matter",
                               db_path=str(routes_kb.KB_DB),
                               source_filename="nope.txt")

    def test_scope_requires_matter(self):
        with self.assertRaises(ValueError):
            retrieval.retrieve("anything", matter=None,
                               db_path=str(routes_kb.KB_DB),
                               source_filename="b.txt")

    def test_default_none_is_unscoped(self):
        a = retrieval.retrieve("indemnification", matter="scope-matter",
                               db_path=str(routes_kb.KB_DB))
        b = retrieval.retrieve("indemnification", matter="scope-matter",
                               db_path=str(routes_kb.KB_DB), source_filename=None)
        self.assertEqual(a, b)
```

- [ ] **Step 2: Implement in retrieval.py**

```python
def _scope_filter(table, matter, source_filename, cache_key):
    """source_filename hard pre-filter (G-SCOPE). Requires a matter (scoping is
    within-matter only) and validates against the store's filenames FOR THAT
    MATTER, so a typo can never silently become search-all."""
    if source_filename is None:
        return None
    if matter is None:
        raise ValueError("source_filename scoping requires a matter")
    names = {r["source_filename"] for r in
             table.search().select(["source_filename", "matter"])
                  .where(f"matter = '{matter.replace(chr(39), chr(39) * 2)}'",
                         prefilter=True)
                  .limit(table.count_rows()).to_arrow().to_pylist()}
    if source_filename not in names:
        raise ValueError(f"unknown document in matter: {source_filename!r}")
    return f"source_filename = '{source_filename.replace(chr(39), chr(39) * 2)}'"
```

In `retrieve()`: add the parameter, build `sf = _scope_filter(table, matter, source_filename, key)`, and combine: `filt = f"({filt}) AND ({sf})" if (filt and sf) else (sf or filt)`. Both the dense and FTS arms already flow through `_scoped()` so hybrid inherits it. (Cache the per-matter filename set with the same `_store_matters`-style cache if profiling shows it hot — not speculatively.)

- [ ] **Step 3: Tests green; commit** (`feat(retrieval): source_filename hard pre-filter (G-SCOPE)`)

### Task D2: Thread scope through `answer()` / `answer_stream()`

**Files:** `pipeline/answering.py` (signatures at lines 423/478 pass `source_filename` straight to `retrieve`); `pipeline/tests/test_retrieval_scope.py` (add one integration test: scoped answer about indemnification against the temp store cites only b.txt or refuses — requires Ollama; mark with the repo's existing live-test pattern).
**Interfaces:** `answer(question, matter=None, top_k=5, db_path=None, with_confidence=False, source_filename=None)` — default None byte-identical.

### Task D3: Single-document review actually scopes

**Files:** `pipeline/clauses.py` (`iter_clauses` passes `source_filename=target_filename` into `answer()`; the existing post-filter stays as belt-and-braces); `pipeline/tests/test_clauses.py` (mocked-answer test asserting the kwarg reaches `answer`).

```python
# clauses.iter_clauses inner call becomes:
res = answer(clause["question"], matter=matter, top_k=top_k, db_path=db_path,
             source_filename=target_filename)
```

### Task D4: Grid negative-cell verification pass

**Files:** `pipeline/grid.py`, `pipeline/routes_grid.py` (new `cell-verify` SSE event), `pipeline/static/app.js` (`fillGridCell` accepts upgrades), `pipeline/tests/test_grid.py`.
**Interfaces:** `run_grid(...)` yields, after the memoized pass, one upgraded cell dict per formerly-negative cell with `"verified_scope": "document"`; call count = questions + negative_cells (test with a counting fake: 2 docs x 2 questions where one refusal flips to found under scope -> exactly 4 + 2 answer() calls... write the arithmetic into the test).

### Task D5: Matter-checklist absence verification in the review job

**Files:** `pipeline/review_job.py` (after the streamed pass: for each `potentially_missing` row, scoped re-asks per doc honoring the doc-type filter; emit `verify` events; upgrade rows; summary gains `verified_absences`), `pipeline/static/app.js` (progress copy "Verifying absences in each document (N of M)…", upgraded label "Not located in <N> documents (every document checked individually)"), `pipeline/tests/test_review_jobs.py` (mocked answer where clause X refuses matter-wide but is found when scoped to doc 2 -> final row is `found` with the citation; and a true absence ends verified with the per-document label).

### Task D6: The gate cycle + release v0.6.0

- [ ] Full dev suite vs baseline; `node --check`.
- [ ] Eval repo: `run_golden.py v060-gate` -> `score_golden.py` MUST read exactly `63/63, 9/9, 0 rejected` (unscoped path byte-identical; any drift = STOP, diagnose, do not rationalize).
- [ ] New G-SCOPE proof against the eval store: scoped ask for a clause known present in ONE doc of a multi-doc matter returns it; the same ask scoped to a doc lacking it refuses. Add to `pipeline/tests/test_retrieval_scope.py` as the live-integration class.
- [ ] Packaged build + full smoke (incl. OCR + review-SSE steps); adversarial review of the whole workstream; draft release; owner click-through; publish.

---

## Sequencing and estimates

| Order | Task | Size | Engine? |
|---|---|---|---|
| 1 | A1 label demotion | ~half day | no |
| 2 | C1 RAM gate | ~1 day | no |
| 3 | B1+B2 tesseract bundle | ~1 day (dylib fiddliness budgeted) | no |
| 4 | B3 subfolder recursion | ~half day | no |
| 5 | C2 ship v0.5.1 | ~half day | no (verify zero engine diff) |
| 6 | D1-D2 scoped retrieve/answer | ~1 day | YES |
| 7 | D3 single-doc scope | ~half day | YES |
| 8 | D4 grid verify pass | ~1 day | YES |
| 9 | D5 checklist absence verify | ~1-2 days | YES |
| 10 | D6 gate + ship v0.6.0 | ~1 day | gate |

Council riders throughout: adversarial review per task; no distribution push until 1-9 land; the export caveat stays until D6 ships, then updates to name the per-document verification.
