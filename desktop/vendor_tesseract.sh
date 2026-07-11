#!/usr/bin/env bash
# desktop/vendor_tesseract.sh — copy the build machine's Tesseract into
# desktop/vendor/tesseract with RELOCATABLE dylibs (@executable_path), so the
# packaged app OCRs scanned PDFs with zero user installs. Build-machine
# prerequisites:
#   brew install tesseract dylibbundler
# Idempotent: skips if a COMPLETE vendor tree already exists (binary + dylibs +
# eng.traineddata). After `brew upgrade tesseract`, delete desktop/vendor/tesseract
# to re-vendor. Vendoring is staged in a temp dir and moved into place atomically,
# so a failed run can never leave a half-vendored tree that later builds skip over.
set -euo pipefail
cd "$(dirname "$0")/.."
VENDOR="desktop/vendor/tesseract"

if [[ -x "$VENDOR/bin/tesseract" && -f "$VENDOR/share/tessdata/eng.traineddata" ]] \
   && ls "$VENDOR/lib/"*.dylib >/dev/null 2>&1; then
  echo "==> tesseract already vendored"
  exit 0
fi

TES="$(command -v tesseract || true)"
[[ -n "$TES" ]] || { echo "ERROR: brew install tesseract first" >&2; exit 1; }
command -v dylibbundler >/dev/null || { echo "ERROR: brew install dylibbundler" >&2; exit 1; }

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/bin" "$STAGE/lib" "$STAGE/share/tessdata"
cp "$TES" "$STAGE/bin/tesseract"
chmod u+w "$STAGE/bin/tesseract"
# rewrite every non-system dylib reference to @executable_path/../lib
dylibbundler -of -b -x "$STAGE/bin/tesseract" -d "$STAGE/lib" -p '@executable_path/../lib'
TESSDATA="$(brew --prefix tesseract)/share/tessdata"
cp "$TESSDATA/eng.traineddata" "$STAGE/share/tessdata/"
cp "$TESSDATA/osd.traineddata" "$STAGE/share/tessdata/" 2>/dev/null || true

# relocation assert: NO brew-prefixed load command may remain anywhere in the
# tree (a --version smoke on the build machine would pass even un-rewritten)
if otool -L "$STAGE/bin/tesseract" "$STAGE/lib/"*.dylib | grep -F "$(brew --prefix)"; then
  echo "ERROR: brew-prefixed load commands remain — binary is not relocatable" >&2
  exit 1
fi
"$STAGE/bin/tesseract" --version >/dev/null || { echo "ERROR: vendored binary broken" >&2; exit 1; }

rm -rf "$VENDOR"
mkdir -p "$(dirname "$VENDOR")"
mv "$STAGE" "$VENDOR"
trap - EXIT
chmod 755 "$VENDOR"
echo "==> vendored tesseract: $("$VENDOR/bin/tesseract" --version 2>&1 | head -1)"
