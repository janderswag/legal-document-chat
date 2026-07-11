#!/usr/bin/env bash
# One-command macOS build of docuchat.app (P2.7): bundle -> (sign -> notarize -> staple) -> DMG.
#
#   ./desktop/build_macos.sh
#
# Run from the repo root inside the project venv (needs: pip install pyinstaller pywebview).
# Signing/notarization run ONLY when the env vars below are set; without them the script
# still produces an UNSIGNED dist/docuchat.app + docuchat-unsigned.dmg for local testing
# and prints exactly what is missing. See desktop/SIGNING.md for the one-time setup.
#
#   APPLE_DEV_ID_APP   e.g. 'Developer ID Application: Jake Anderson (TEAM123456)'
#   NOTARY_PROFILE     notarytool keychain profile name (SIGNING.md step 3)
#
# Optional: BUNDLE_OLLAMA=1 downloads the Ollama darwin binary into desktop/vendor/ so it
# ships silently inside the app (interim per P2.7; the launcher prefers a user install).

set -euo pipefail
cd "$(dirname "$0")/.."

VENDOR="desktop/vendor"
APP="dist/docuchat.app"
DMG="dist/docuchat.dmg"

if [[ "${BUNDLE_OLLAMA:-0}" == "1" && ! -f "$VENDOR/ollama" ]]; then
  echo "==> Downloading Ollama (darwin) into $VENDOR ..."
  mkdir -p "$VENDOR"
  curl -fL --progress-bar -o "$VENDOR/ollama.tgz" \
    "https://github.com/ollama/ollama/releases/latest/download/ollama-darwin.tgz"
  tar -xzf "$VENDOR/ollama.tgz" -C "$VENDOR" ollama
  rm -f "$VENDOR/ollama.tgz"
  chmod +x "$VENDOR/ollama"
fi

echo "==> Vendoring Tesseract (scanned-PDF OCR)..."
./desktop/vendor_tesseract.sh

echo "==> Building docuchat.app with PyInstaller..."
pyinstaller --noconfirm --clean desktop/build_macos.spec
[[ -d "$APP" ]] || { echo "ERROR: $APP not produced"; exit 1; }

if [[ -n "${APPLE_DEV_ID_APP:-}" ]]; then
  echo "==> Signing (hardened runtime, deep) as: $APPLE_DEV_ID_APP"
  # The vendored tesseract tree ships as PyInstaller DATA, which lands under
  # Contents/Resources — codesign --deep does NOT sign Mach-Os there (it only
  # seals them into CodeResources), and notarytool rejects the adhoc-signed
  # binaries. Sign them explicitly first.
  TESS_TREE="$APP/Contents/Resources/pipeline/vendor/tesseract"
  if [[ -d "$TESS_TREE" ]]; then
    echo "==> Signing vendored tesseract Mach-Os (Resources are not covered by --deep)"
    find "$TESS_TREE" -type f \( -name '*.dylib' -o -name tesseract \) \
      -exec codesign --force --options runtime --timestamp \
        --sign "$APPLE_DEV_ID_APP" {} +
  fi
  codesign --force --deep --options runtime --timestamp \
    --entitlements desktop/entitlements.plist \
    --sign "$APPLE_DEV_ID_APP" "$APP"
  codesign --verify --deep --strict --verbose=2 "$APP"
else
  echo "==> SKIPPING signing: APPLE_DEV_ID_APP not set (SIGNING.md step 2)."
fi

echo "==> Creating DMG..."
rm -f "$DMG" dist/docuchat-unsigned.dmg
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
if [[ -n "${APPLE_DEV_ID_APP:-}" ]]; then
  hdiutil create -volname "docuchat" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
  codesign --force --timestamp --sign "$APPLE_DEV_ID_APP" "$DMG"
else
  DMG="dist/docuchat-unsigned.dmg"
  hdiutil create -volname "docuchat" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
fi
rm -rf "$STAGE"

if [[ -n "${APPLE_DEV_ID_APP:-}" && -n "${NOTARY_PROFILE:-}" ]]; then
  echo "==> Notarizing (this waits on Apple; typically a few minutes)..."
  xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
  echo "==> Stapling ticket..."
  xcrun stapler staple "$DMG"
  xcrun stapler staple "$APP"
  echo "==> Gatekeeper check:"
  spctl --assess --type open --context context:primary-signature -v "$DMG" || true
  spctl --assess --type execute -v "$APP"
else
  [[ -n "${APPLE_DEV_ID_APP:-}" ]] && \
    echo "==> SKIPPING notarization: NOTARY_PROFILE not set (SIGNING.md step 3)." || true
fi

if [[ "${SKIP_SMOKE:-0}" == "1" ]]; then
  echo "==> WARNING: SKIPPING the packaged-app smoke gate (SKIP_SMOKE=1)."
  echo "==>          This bundle has been BUILT but NOT PROVEN TO WORK. Do not ship it"
  echo "==>          without running ./desktop/smoke_packaged.sh $APP first."
else
  echo "==> Running packaged-app smoke gate (desktop/smoke_packaged.sh) ..."
  ./desktop/smoke_packaged.sh "$APP"
fi

echo "==> Done: $DMG"
