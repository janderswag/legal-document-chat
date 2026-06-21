#!/usr/bin/env bash
# SC-7 — restore a LanceDB store from a local tarball into a target directory.
#
# Usage: deploy/restore.sh <store.tar.gz> [target_dir]
#   target_dir defaults to pipeline/.lancedb_restored (a SCRATCH dir) so the drill
#   NEVER overwrites the live pipeline/.lancedb that backs M2-8. For a real restore on a
#   clean machine, pass the production volume path as target_dir.
#
# Local file operation only — no network, no public bind, no host-override.
set -euo pipefail

TARBALL="${1:?usage: restore.sh <store.tar.gz> [target_dir]}"
TARGET="${2:-pipeline/.lancedb_restored}"
cd "$(dirname "$0")/.."   # repo root

if [ ! -f "$TARBALL" ]; then
  echo "[restore] ERROR: tarball not found: $TARBALL" >&2
  exit 1
fi

echo "[restore] restoring $TARBALL -> $TARGET"
rm -rf "$TARGET"
mkdir -p "$TARGET"
tar -xzf "$TARBALL" -C "$TARGET"
echo "[restore] done: $(find "$TARGET" -type f | wc -l | tr -d ' ') files restored to $TARGET"
