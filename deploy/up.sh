#!/usr/bin/env bash
# SC-7 — bring up the loopback FastAPI stack from scripts (compose-only, D-43a).
# Builds the image and starts the single service, then health-checks over loopback.
# Publishes a loopback bind only (via compose); does not override the host Ollama bind,
# which stays on 127.0.0.1:11434.
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root (where docker-compose.yml lives)

echo "[up] docker compose up -d --build"
docker compose up -d --build

echo "[up] waiting for http://127.0.0.1:8000/health ..."
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "[up] healthy: $(curl -s http://127.0.0.1:8000/health)"
    exit 0
  fi
  sleep 1
done

echo "[up] ERROR: service did not become healthy on 127.0.0.1:8000" >&2
docker compose logs --tail 30 || true
exit 1
