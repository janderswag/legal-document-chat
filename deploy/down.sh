#!/usr/bin/env bash
# SC-7 — tear the stack down (compose-only) and verify the loopback port is released.
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root

echo "[down] docker compose down"
docker compose down

if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[down] ERROR: 127.0.0.1:8000 still bound after compose down" >&2
  exit 1
fi
echo "[down] port 8000 released; no lingering bind"
