# PyInstaller spec — docuchat Windows build (D-61 scaffold).
#
# BUILD ON WINDOWS ONLY. PyInstaller does not cross-compile, so this is never run on the Mac
# (it is intentionally NOT a dependency of the Mac venv). On the owner's Windows box, from the
# repo root inside the project venv:
#
#     pyinstaller desktop/build_windows.spec
#
# This is a best-effort starting point: torch / docling / lancedb / tesseract pull data files and
# dynamically-imported submodules that PyInstaller can miss. Expect to iterate on `hiddenimports`
# and `datas` (see desktop/WINDOWS_TEST.md "Known gaps / iterate here").

import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
REPO = os.path.abspath(os.getcwd())
PIPELINE = os.path.join(REPO, "pipeline")

# LOAD-BEARING: collect_submodules("connectors") below imports the "connectors" package to
# walk it, so it silently returns [] unless pipeline/ is already on sys.path at spec-eval
# time. build_macos.spec only avoids this by accident (its sys.path.insert is there for the
# appversion import, not for this) — without it here too, the Windows build ships the same
# empty-connector-registry regression the Mac build shipped (connectors-audit.md root cause).
sys.path.insert(0, PIPELINE)

datas = []
binaries = []
hiddenimports = []

# Packages that load data files and/or dynamically import submodules at runtime.
for pkg in (
    "torch", "transformers", "tokenizers", "safetensors",
    "docling", "docling_core", "docling_ibm_models",
    "lancedb", "pylance", "pyarrow",
    "fitz", "pymupdf", "pytesseract",
    "fastapi", "uvicorn", "starlette", "pydantic", "pydantic_core",
):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass  # package not importable at spec time — owner resolves on Windows

hiddenimports += collect_submodules("uvicorn")
# connectors/__init__.py discovers its 28 adapter modules dynamically at runtime via
# pkgutil.iter_modules — there is no literal `import connectors.gmail` etc. anywhere for
# PyInstaller's static analysis to see, so without this the frozen registry is empty and
# every connector in the UI is inert (connectors-audit.md root cause).
hiddenimports += collect_submodules("connectors")
# api lives at pipeline/api.py (on pathex below); launcher imports it lazily (frozen
# in-process path), and api/routes_matters import sample_matter inside functions -
# static analysis misses all three.
hiddenimports += ["api", "sample_matter"]

# Ship the pipeline's static UI + JSON data next to the exe.
for rel in ("static", "data"):
    src = os.path.join(PIPELINE, rel)
    if os.path.isdir(src):
        datas.append((src, f"pipeline/{rel}"))

a = Analysis(
    [os.path.join(REPO, "desktop", "launcher.py")],
    pathex=[REPO, PIPELINE],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="docuchat-setup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI app (pywebview window); no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # TODO: add desktop/docuchat.ico derived from site/favicon.svg
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="docuchat-setup",
)
