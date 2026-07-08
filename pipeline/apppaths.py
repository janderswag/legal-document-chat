"""Where the app READS bundled assets and WRITES user data, dev vs frozen.

Run-from-source (dev, tests, evals): everything stays exactly where it has always
been — data under pipeline/ and documents/kb under the repo root. Nothing changes.

FROZEN (PyInstaller .app): the first real launch of the packaged app (P2.7
verification) showed both defaults are wrong there:
  - assets: datas land at ``_MEIPASS/pipeline/...``, not ``_MEIPASS/...`` (the
    module-relative guess) — the / page 500'd on a missing static/index.html;
  - data: module-relative writes land INSIDE the .app bundle
    (Contents/Frameworks/.kb_catalog.db was created on first run). A signed
    bundle must never mutate itself, and app updates would destroy client data.
So frozen builds read assets from the bundle and write all durable data to
``~/Library/Application Support/docuchat/``.
"""

import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
IS_FROZEN = bool(getattr(sys, "frozen", False))


def assets_root():
    """Read-only bundled assets (static UI, data seeds). Dev: pipeline/."""
    if IS_FROZEN:
        return Path(sys._MEIPASS) / "pipeline"
    return PIPELINE_DIR


def data_root():
    """Writable durable data (catalog, KB store, encrypted bundle). Dev: pipeline/."""
    if IS_FROZEN:
        p = Path.home() / "Library" / "Application Support" / "docuchat"
        p.mkdir(parents=True, exist_ok=True)
        return p
    return PIPELINE_DIR


def docs_root():
    """Managed document copies (documents/kb). Dev: <repo>/documents/kb."""
    if IS_FROZEN:
        return data_root() / "documents" / "kb"
    return PIPELINE_DIR.parent / "documents" / "kb"
