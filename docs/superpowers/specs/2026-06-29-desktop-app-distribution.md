# Desktop app distribution — downloadable, click-to-open app (design)

> **Status: design / research captured 2026-06-29. Owner-directed.** Goal: let a user download a
> double-clickable app from a website (macOS + Windows) instead of self-hosting via terminal/Docker.
> Owner decisions: **phased A → B** (launcher first, then full one-click app) and **wrap, don't rewrite**
> (keep the entire Python pipeline + the mechanical citation verifier — our moat — untouched). Research
> backed by two cited research passes (Tauri/packaging feasibility; competitive teardown of LM Studio,
> Jan, GPT4All, Ollama app, AnythingLLM, Msty). See `DECISIONS.md` D-58.

## The problem, framed honestly
A desktop wrapper only provides an installable window. "Download → double-click → use" has **two hard
blockers, neither of which is the web server:**
1. **Heavy Python backend.** Freezing FastAPI + PyMuPDF + Docling (pulls **PyTorch, multi-GB**) +
   Tesseract + LanceDB with PyInstaller yields a **2–5 GB installer before any model**, needs 3 build
   machines (mac-arm, mac-x64, win-x64; no cross-compile), and is fiddly to package/sign. **No comparable
   shipped app uses a Python backend** — all use embedded native engines (C++/Go/Rust/Node + llama.cpp).
2. **External Ollama + ~10 GB models.** The real "click and use" killer. Every successful peer **embeds
   the engine in the installer** and **downloads models in-app on first run** with a progress bar.

## Dominant pattern (the non-negotiable lessons)
- **Ship the engine, not the model.** Installer carries the engine + UI (tens–hundreds of MB); models
  download in-app on first run into a cache dir; subsequent launches are fully offline.
- **Keep the backend we have** (wrap, don't rewrite) — rewriting native would discard the citation
  verifier, which is the whole product. Rejected.

## Framework decision: **pywebview/tray launcher recommended over Tauri**
Our UI is **already vanilla HTML/JS served over loopback**, so we do NOT need Tauri's Rust IPC bridge.
- **pywebview (or a menu-bar/tray app)** = pure Python, ships the *same* PyInstaller bundle we'd ship
  anyway, **no Rust, no per-arch sidecar gymnastics**. Lowest moving-part count for a solo maintainer.
- **Tauri v2** remains viable (privacy-aligned tiny Rust shell, good signing tooling) but its bundle-size
  advantage evaporates behind a multi-GB Python sidecar, and it adds Rust + DIY sidecar lifecycle
  (orphaned-process/port bugs are well documented). Use only if we want a "real native app" feel.
- Electron: best Python-sidecar precedent but +Chromium and a runtime privacy-conscious users side-eye.
**Decision: pywebview/tray for both phases; revisit Tauri only if a native-app feel is required.**

## Phase A — Launcher (cheap, technical audience, ships first)
A tray/menu-bar (or pywebview) launcher that wraps the **existing** FastAPI app: starts the server,
health-checks `127.0.0.1:8000`, opens the UI in a window, stops the server on quit. **Still requires the
user to have Ollama + models** (documented). **Unsigned is acceptable here** — technical users click
through OS warnings; **$0 signing**. Kills the "open a terminal" friction. Reuses 100% of the pipeline.

## Phase B — Full one-click app (attorneys)
Phase A + the two hard problems solved:
- **Embed the inference engine as a sidecar** (bundle Ollama, or an llama.cpp/llama-server, launched +
  killed by the app) so there is **no separate Ollama install**. This is what makes it truly one-click.
- **In-app first-run model download** with a progress bar (qwen3:14b + bge-m3), into a cache dir; offline
  thereafter. Provide an **offline/sideload installer option** so the air-gap promise survives (see below).
- **PyInstaller-freeze the Python backend** as a sidecar; CPU-only Torch + aggressive `--exclude`/`.spec`
  work to shrink the bundle; per-arch builds via CI.
- **Signed + notarized installers** (see costs) + a simple website download page.

## Code-signing & notarization (the trust tax, not a distribution toll)
Unsigned apps still download and run — they just show "unidentified developer / unknown publisher"
warnings. Removing those warnings:
- **macOS:** Apple Developer Program **$99/yr** + Developer ID + notarization → app opens with no warning.
  Unsigned (post-Sequoia 15.1) forces a System-Settings bypass — a conversion killer for attorneys.
- **Windows:** unsigned → SmartScreen "unknown publisher." Cheapest sane path = **Azure Trusted Signing
  ~$10/mo**. Note: even signed, Windows "reputation" warms up over download volume (EV no longer instant).
- **Budget:** ~**$220/yr** total. **Phase A skips signing ($0); Phase B needs it** for the attorney audience.

## Privacy / air-gap guardrails (must not erode the moat)
- First-run model download **dents the air-gap story** → make it **explicit, checksum-verified, and offer
  a fully-offline model installer**. Query path stays loopback-only.
- **No telemetry, no silent auto-update phone-home.** Updates must be opt-in/disclosed. Signing keys never
  committed (already covered by hardened `.gitignore`).
- The bundled engine/model download is the ONLY new network activity, and only at setup.

## Top risks
1. **PyInstaller + native deps (Torch/Docling/Tesseract) will not "just work"** — custom `.spec`, days of
   work, likely `--onedir` for clean signing.
2. **3 build machines / CI runners** (no cross-compile) — biggest hidden solo-dev ops cost.
3. **Sidecar lifecycle** (orphaned Python/engine processes holding port 8000) — must hold the child handle
   and kill on exit + pre-kill the port on launch.
4. **2–5 GB bundle before models + ~10 GB models** — honest user story; mitigate with CPU-only Torch,
   first-run download, and optional/offline model installer.
5. **Windows reputation lag** even when signed — plan first-run docs/messaging.

## Deferred / explicitly out of scope for v1
Trimming Docling/Torch out of the default bundle (owner chose wrap-don't-rewrite); auto-update
infrastructure; Linux packaging; App Store / Microsoft Store distribution; bundling models into the
installer.

## Sequencing (when greenlit — separate from the relay; this is a packaging effort, not pipeline code)
1. **Phase A launcher** prototype (pywebview/tray around current FastAPI) → unsigned dev builds for
   mac-arm + win-x64 → "it opens in a window" proof.
2. Decide signing + set up CI build matrix.
3. **Phase B**: engine sidecar + in-app model download → PyInstaller backend sidecar → signed/notarized
   installers → website download page.
