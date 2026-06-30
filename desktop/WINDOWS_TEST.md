# Windows build + test runbook (docuchat, Phase A → Windows)

> **This is the owner's runbook.** The Mac cannot build or test a Windows `.exe` (PyInstaller does
> not cross-compile), so this is run on your **Windows machine**. The Mac side only **scaffolds**:
> `build_windows.spec`, `build_windows.ps1`, the cross-platform `launcher.py`, and this file.
> The landing page keeps the **Windows download button disabled ("soon")** until you produce and
> attach `docuchat-setup.exe` to a GitHub Release. (D-61)

Loopback-only, no telemetry — same hard rules as the Mac build. Use **synthetic/sample documents
only**, never real client data.

---

## 1. Prerequisites (install once)

1. **Python 3.11+ (64-bit)** from python.org. During install, tick **"Add python.exe to PATH."**
   Verify in a new PowerShell:
   ```powershell
   python --version
   ```
2. **Git** (to clone the repo) — https://git-scm.com/download/win
3. **Ollama for Windows** — https://ollama.com/download — install and let it run (it listens on
   `127.0.0.1:11434`). Then pull the two pinned models:
   ```powershell
   ollama pull qwen3:14b
   ollama pull bge-m3
   ```
4. **Tesseract OCR (Windows)** — https://github.com/UB-Mannheim/tesseract/wiki — install and add its
   folder (e.g. `C:\Program Files\Tesseract-OCR`) to PATH. Needed for scanned-PDF OCR.

## 2. Get the code + a virtual environment

```powershell
git clone https://github.com/janderswag/legal-document-chat.git
cd legal-document-chat
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## 3. Install dependencies (into the venv)

```powershell
# the app's runtime deps
pip install -r pipeline\requirements.txt
# the desktop launcher (pywebview uses the native Edge WebView2 runtime on Windows)
pip install -r desktop\requirements.txt
# the build tool — Windows only, NEVER added to the Mac venv
pip install pyinstaller
```

> If `pipeline\requirements.txt` is heavy (torch/docling), this step is the long one. Let it finish.
> On Windows, pywebview renders with **WebView2**; if the window is blank, install the
> "Microsoft Edge WebView2 Runtime" (evergreen) from Microsoft and retry.

## 4. Smoke-test BEFORE freezing (catches most issues fast)

Run the launcher straight from source first. This proves the server + window + Ollama detection
work on your machine before PyInstaller is involved:

```powershell
python desktop\launcher.py
```
Expect: a window titled **docuchat** opens on `http://127.0.0.1:8000/setup`. The first-run wizard
checks for Ollama + the two models; when present it drops into `/app`. Close the window — confirm
no `python.exe` is left running (Task Manager) and port 8000 is free:
```powershell
netstat -ano -p tcp | findstr :8000
```
(Should print nothing once closed — the cross-platform `taskkill /T` cleanup reaped the child.)

## 5. Build the executable

```powershell
powershell -ExecutionPolicy Bypass -File desktop\build_windows.ps1
```
Output: **`dist\docuchat-setup\docuchat-setup.exe`** (a one-folder build — ship the whole
`dist\docuchat-setup\` folder, zipped, not just the bare `.exe`).

## 6. Run + verify the built app

Double-click `dist\docuchat-setup\docuchat-setup.exe` (or run it from PowerShell to see errors).
Verify:

- [ ] The **docuchat** window opens (the first-run wizard at `/setup`).
- [ ] **Ollama detection** works — with Ollama running + both models pulled, the wizard advances to
      the app; with a model missing, it shows the `ollama pull ...` guidance.
- [ ] **Loopback-only binding** — the server is on `127.0.0.1:8000` and nothing binds `0.0.0.0`:
      ```powershell
      netstat -ano -p tcp | findstr LISTENING | findstr :8000
      ```
      The local address must be `127.0.0.1:8000`, never `0.0.0.0:8000`.
- [ ] Ask a question against a **sample** document and confirm a cited answer renders.
- [ ] Close the window → no orphaned `docuchat-setup.exe` / `python` process; port 8000 frees.

## 7. The SmartScreen "unknown publisher" warning

The build is **unsigned** (code-signing is Phase B). On first run, Windows SmartScreen will show
**"Windows protected your PC."** To proceed:

1. Click **More info**.
2. Click **Run anyway**.

This is expected for an unsigned Phase-A binary. Note it on the download page / Release notes so
users aren't alarmed. (A real Authenticode certificate removes this in Phase B.)

## 8. Attach the build to a GitHub Release

1. Zip the one-folder build:
   ```powershell
   Compress-Archive -Path dist\docuchat-setup\* -DestinationPath docuchat-setup-win64.zip
   ```
2. On GitHub → **Releases** → **Draft a new release** (or edit the existing one).
3. Drag `docuchat-setup-win64.zip` into the **Assets** box and publish.
4. Tell the Planner: the landing page's Windows button can flip from **"soon"** to a live link to
   that asset.

---

## Known gaps / iterate here (expected — this is a scaffold)

- **Frozen subprocess model.** `launcher.py` starts the server with
  `sys.executable -m uvicorn api:app`. Inside a PyInstaller bundle, `sys.executable` is the frozen
  exe (not a Python interpreter), so `-m uvicorn` will not work as-is. The cleanest fix is a
  **frozen-aware start**: when `getattr(sys, "frozen", False)`, run uvicorn **in-process / in a
  thread** (`uvicorn.run(api.app, host="127.0.0.1", port=8000)`) instead of spawning. Keep it
  loopback-only. (Left out of the Mac batch to avoid touching tested launch behavior; wire it here.)
- **hiddenimports / datas.** torch, docling, lancedb, and pyarrow load submodules and data files
  dynamically; if the exe crashes on a `ModuleNotFoundError` or a missing data file, add the module
  to `hiddenimports` or the file/dir to `datas` in `build_windows.spec` and rebuild.
- **Tesseract binary** is a separate native install (step 1.4); it is not bundled. The app shells
  out to `tesseract` on PATH.
- **Icon.** `build_windows.spec` has `icon=None`. Derive a `desktop\docuchat.ico` from
  `site/favicon.svg` and set it for a branded exe + window icon.
- **HF model cache.** Reranker/TableFormer weights live in `~/.cache/huggingface`, fetched once then
  used offline; they are **not** bundled. First use of a table-heavy PDF may fetch them once.
