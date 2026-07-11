# PyInstaller spec — docuchat macOS .app bundle (P2.7).
#
# Build on macOS from the repo root inside the project venv:
#
#     pyinstaller desktop/build_macos.spec
#
# Produces dist/docuchat.app. Signing/notarization/DMG happen in desktop/build_macos.sh
# (codesign identity comes from the environment there — never hardcoded here).
#
# Like the Windows spec, this is a working starting point: torch / docling / lancedb pull
# data files and dynamically-imported submodules PyInstaller can miss; iterate on
# `hiddenimports`/`datas` against a real run (desktop/SIGNING.md "Verify the bundle").

import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
REPO = os.path.abspath(os.getcwd())
PIPELINE = os.path.join(REPO, "pipeline")

# Single source of truth for the version (pipeline/appversion.py) — a hardcoded copy
# here once stamped a v0.4.0 build as 0.3.2.
sys.path.insert(0, PIPELINE)
from appversion import APP_VERSION

datas = []
binaries = []
hiddenimports = []

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
        pass  # package not importable at spec time — resolve while iterating

hiddenimports += collect_submodules("uvicorn")
# connectors/__init__.py discovers its 28 adapter modules dynamically at runtime via
# pkgutil.iter_modules — there is no literal `import connectors.gmail` etc. anywhere for
# PyInstaller's static analysis to see, so without this the frozen registry is empty and
# every connector in the UI is inert (connectors-audit.md root cause).
hiddenimports += collect_submodules("connectors")
# The app module tree: launcher imports api lazily (frozen in-process path), and api /
# routes_matters import sample_matter inside functions — static analysis misses those.
hiddenimports += ["api", "sample_matter"]

# Ship the pipeline's static UI + JSON data inside the bundle.
for rel in ("static", "data"):
    src = os.path.join(PIPELINE, rel)
    if os.path.isdir(src):
        datas.append((src, f"pipeline/{rel}"))

# Silently bundled Ollama (P2.7 interim): build_macos.sh downloads the binary to
# desktop/vendor/ollama first; find_ollama() looks for it under Contents/MacOS/resources.
_ollama = os.path.join(REPO, "desktop", "vendor", "ollama")
if os.path.isfile(_ollama):
    binaries.append((_ollama, "resources"))

# Vendored Tesseract (adoption council 2026-07-11): build_macos.sh runs
# desktop/vendor_tesseract.sh first (relocatable binary + dylibs + tessdata).
# Target is pipeline/vendor/tesseract because ingestion.configure_tesseract()
# resolves it via apppaths.assets_root(), which is _MEIPASS/pipeline when frozen.
_tesseract = os.path.join(REPO, "desktop", "vendor", "tesseract")
if os.path.isdir(_tesseract):
    datas.append((_tesseract, "pipeline/vendor/tesseract"))

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
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="docuchat",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,            # GUI app (pywebview window)
    disable_windowed_traceback=False,
    target_arch=None,         # build per-arch; universal2 needs a universal Python
    codesign_identity=None,   # signing happens in build_macos.sh
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="docuchat",
)
app = BUNDLE(
    coll,
    name="docuchat.app",
    icon=None,                # TODO: desktop/docuchat.icns derived from site/favicon.svg
    bundle_identifier="app.docuchat.desktop",
    info_plist={
        "CFBundleName": "docuchat",
        "CFBundleDisplayName": "docuchat",
        "CFBundleShortVersionString": APP_VERSION,
        "NSHighResolutionCapable": True,
        # pywebview uses WKWebView against 127.0.0.1 only; no ATS exception needed for
        # loopback. No microphone/camera/location usage strings — the app asks for none.
    },
)
