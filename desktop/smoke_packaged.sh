#!/usr/bin/env bash
# Packaged-app smoke gate (Sprint 1, connectors-audit.md "institutional fix"):
# proves the REAL frozen .app works, not just the source tree. Three prior incidents
# (this connectors bug, the WKWebView upload bug, the keychain incident) all shipped
# with green source tests and a broken bundle — this script is the check that catches
# that class of bug before a release goes out.
#
#   ./desktop/smoke_packaged.sh [path/to/docuchat.app]
#
# Defaults to dist/docuchat.app (what build_macos.sh produces). Runs the app's REAL
# server (the same Contents/MacOS/docuchat binary, headless via DOCUCHAT_SMOKE=1 — see
# desktop/launcher.py) against a SCRATCH port + SCRATCH data dir, so it never touches
# the owner's live app on 8000 or ~/Library/Application Support/docuchat. Loopback only.
#
# Exits non-zero with a clear message on ANY failure. Always kills the app process and
# removes the scratch dir on exit (success, failure, or interrupt).

set -uo pipefail
cd "$(dirname "$0")/.."

APP="${1:-dist/docuchat.app}"
BIN="$APP/Contents/MacOS/docuchat"
PORT=18731                       # far from the real app's 8000; loopback only
HOST="127.0.0.1"
BASE="http://$HOST:$PORT"
HEALTH_TIMEOUT=120
UPLOAD_TIMEOUT=90

if [[ ! -x "$BIN" ]]; then
  echo "FAIL: $BIN not found or not executable (build the app first: ./desktop/build_macos.sh)" >&2
  exit 1
fi

# Refuse to run against a port already in use — never guess our way onto the owner's
# real app or another process.
if lsof -ti "tcp:$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "FAIL: port $PORT is already in use — pick a different scratch port" >&2
  exit 1
fi

SCRATCH_DIR="$(mktemp -d "${TMPDIR:-/tmp}/docuchat-smoke.XXXXXX")"
APP_PID=""
FAILED=0

cleanup() {
  if [[ -n "$APP_PID" ]] && kill -0 "$APP_PID" 2>/dev/null; then
    kill -TERM "$APP_PID" 2>/dev/null
    for _ in $(seq 1 20); do
      kill -0 "$APP_PID" 2>/dev/null || break
      sleep 0.2
    done
    if kill -0 "$APP_PID" 2>/dev/null; then
      kill -KILL "$APP_PID" 2>/dev/null
      for _ in $(seq 1 20); do
        kill -0 "$APP_PID" 2>/dev/null || break
        sleep 0.2
      done
    fi
  fi
  # D-73 (encvol.py) mounts an encrypted APFS volume at <scratch>/.lancedb_kb on
  # first launch; a hard kill can race the app's own on-shutdown eject
  # (api.py _eject_encrypted_store), leaving it mounted and "Resource busy" for rm.
  # Detach it ourselves — idempotent no-op if the app already ejected it cleanly.
  kb_mount="$SCRATCH_DIR/.lancedb_kb"
  if [[ -d "$kb_mount" ]] && diskutil info "$kb_mount" >/dev/null 2>&1; then
    hdiutil detach "$kb_mount" -force >/dev/null 2>&1
  fi
  # lancedb/mmap handles can take a beat to release after the process actually dies
  # (macOS "Resource busy") — retry the removal a few times before giving up.
  for _ in $(seq 1 10); do
    rm -rf "$SCRATCH_DIR" 2>/dev/null && break
    sleep 0.5
  done
}
trap cleanup EXIT INT TERM

fail() {
  echo "FAIL: $1" >&2
  FAILED=1
  exit 1
}

echo "==> Scratch dir: $SCRATCH_DIR"
echo "==> Launching $BIN headless on $BASE (DOCUCHAT_SMOKE=1) ..."
DOCUCHAT_SMOKE=1 DOCUCHAT_PORT="$PORT" DOCUCHAT_DATA_DIR="$SCRATCH_DIR" "$BIN" \
  >"$SCRATCH_DIR/app.log" 2>&1 &
APP_PID=$!

# --- poll until healthy (timeout 120s) --------------------------------------------
echo "==> Waiting for /health (timeout ${HEALTH_TIMEOUT}s) ..."
deadline=$((SECONDS + HEALTH_TIMEOUT))
healthy=0
while [[ $SECONDS -lt $deadline ]]; do
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    echo "--- app.log ---" >&2
    cat "$SCRATCH_DIR/app.log" >&2
    fail "app process exited before becoming healthy"
  fi
  if curl -s -o /dev/null -w '%{http_code}' "$BASE/health" 2>/dev/null | grep -q '^200$'; then
    healthy=1
    break
  fi
  sleep 1
done
[[ "$healthy" == "1" ]] || fail "server never became healthy on $BASE within ${HEALTH_TIMEOUT}s"
echo "==> Healthy."

# --- (a) HTTP 200 on / ---------------------------------------------------------
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/")
[[ "$code" == "200" ]] || fail "GET / returned $code, expected 200"
echo "==> (a) GET / -> 200"

# --- (b) /connections/services returns 26+ services (THE regression) ----------
services_json="$(curl -s "$BASE/connections/services")"
svc_count="$(echo "$services_json" | jq '.services | length' 2>/dev/null || echo 0)"
if [[ "$svc_count" -lt 26 ]]; then
  fail "GET /connections/services returned $svc_count services, expected 26+ (connectors packaging regression) — body: $services_json"
fi
echo "==> (b) GET /connections/services -> $svc_count services"

# --- (c) a test .txt upload through the real upload route reaches status ready -
matter_resp="$(curl -s -X POST "$BASE/matters" \
  -H 'content-type: application/json' \
  -d '{"display_name":"Smoke Test Matter"}')"
matter_slug="$(echo "$matter_resp" | jq -r '.slug // empty')"
[[ -n "$matter_slug" ]] || fail "POST /matters did not return a slug — body: $matter_resp"
echo "==> created matter '$matter_slug'"

upload_file="$SCRATCH_DIR/smoke.txt"
echo "This is a small synthetic smoke-test document. Not a real matter." >"$upload_file"
upload_resp="$(curl -s -X POST \
  "$BASE/kb/upload?matter=$matter_slug&filename=smoke.txt&doc_type=document" \
  --data-binary "@$upload_file")"
doc_id="$(echo "$upload_resp" | jq -r '.id // empty')"
[[ -n "$doc_id" ]] || fail "POST /kb/upload did not return a document id — body: $upload_resp"
echo "==> uploaded doc id=$doc_id, polling for status=ready (timeout ${UPLOAD_TIMEOUT}s) ..."

deadline=$((SECONDS + UPLOAD_TIMEOUT))
status=""
while [[ $SECONDS -lt $deadline ]]; do
  status="$(curl -s "$BASE/kb/documents?matter=$matter_slug" \
    | jq -r --arg id "$doc_id" '.documents[] | select((.id|tostring)==$id) | .status' 2>/dev/null)"
  [[ "$status" == "ready" ]] && break
  if [[ "$status" == "error" ]]; then
    fail "document $doc_id ingest failed (status=error)"
  fi
  sleep 1
done
[[ "$status" == "ready" ]] || fail "document $doc_id did not reach status=ready within ${UPLOAD_TIMEOUT}s (last status: '$status')"
echo "==> (c) upload -> status ready"

# --- (d) GET /matters/{slug}/overview returns 200 JSON ------------------------
# Uses the matter created above rather than the app's built-in seeded "Sample Matter":
# that seed only appears once the local Ollama embedder is warm (routes_setup.setup_status
# ready), which can take minutes on a scratch install — not something a smoke gate should
# block a release on. The overview route itself is matter-agnostic (catalog.get_matter
# is the only gate), so this proves the same code path.
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/matters/$matter_slug/overview")
[[ "$code" == "200" ]] || fail "GET /matters/$matter_slug/overview returned $code, expected 200"
overview_json="$(curl -s "$BASE/matters/$matter_slug/overview")"
echo "$overview_json" | jq -e '.deadlines' >/dev/null 2>&1 \
  || fail "GET /matters/$matter_slug/overview did not return valid overview JSON — body: $overview_json"
echo "==> (d) GET /matters/$matter_slug/overview -> 200 JSON"

# --- (e) review job runner streams SSE (v0.5.0 Move 2, D-90) -------------------
# Submit a clause review job for the smoke matter and prove the events stream
# opens and carries the meta event (the skeleton source). We cancel right after:
# the smoke gate proves the PIPE works in the bundle, not model quality (that is
# the golden gate's job) — and a scratch box may not have a warm model at all.
job_resp="$(curl -s -X POST "$BASE/clauses/review-jobs" \
  -H 'content-type: application/json' \
  -d "{\"matter\":\"$matter_slug\"}")"
job_id="$(echo "$job_resp" | jq -r '.id // empty')"
[[ -n "$job_id" ]] || fail "POST /clauses/review-jobs did not return a job id — body: $job_resp"
sse_head="$(curl -s -N --max-time 10 "$BASE/jobs/$job_id/events" | head -c 2000)"
echo "$sse_head" | grep -q "event: meta" \
  || fail "GET /jobs/$job_id/events did not stream the meta event — got: ${sse_head:0:300}"
curl -s -X POST "$BASE/jobs/$job_id/cancel" >/dev/null
echo "==> (e) review job $job_id streams SSE (meta event seen), cancelled cleanly"

# --- (f) bundle version matches pipeline/appversion.py -------------------------
plist_version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' \
  "$APP/Contents/Info.plist" 2>/dev/null)"
app_version="$(python3 -c "import sys; sys.path.insert(0,'pipeline'); from appversion import APP_VERSION; print(APP_VERSION)")"
[[ -n "$plist_version" ]] || fail "could not read CFBundleShortVersionString from $APP/Contents/Info.plist"
[[ "$plist_version" == "$app_version" ]] || \
  fail "bundle version '$plist_version' != pipeline/appversion.APP_VERSION '$app_version'"
echo "==> (f) bundle version $plist_version == appversion.APP_VERSION"

echo "==> SMOKE PASSED: $APP is real and working ($svc_count connectors, upload+overview+version all green)."
exit 0
