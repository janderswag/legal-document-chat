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
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
REPO = os.path.abspath(os.getcwd())
PIPELINE = os.path.join(REPO, "pipeline")

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
hiddenimports += ["api"]  # the FastAPI app module lives at pipeline/api.py (on pathex below)

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
