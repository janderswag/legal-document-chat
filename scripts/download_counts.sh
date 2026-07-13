#!/usr/bin/env bash
# Log GitHub release download counts to a CSV, one row per release per run.
#
# PostHog can tell us someone CLICKED the download button. Only GitHub knows whether the DMG
# was actually fetched. Comparing the two is the whole funnel we are able to see; everything
# after the download is invisible by design (the app has no telemetry).
#
# Usage:  scripts/download_counts.sh            # append today's counts
#         cat eval/download_counts.csv          # read the log
#
# Caveat worth remembering when reading the numbers: GitHub counts every asset fetch,
# including our own release-verification curls. Early rows are mostly the owner.
set -euo pipefail

REPO="janderswag/docuchat.app"
OUT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/eval/download_counts.csv"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [ ! -f "$OUT" ]; then
  echo "measured_at,tag,asset,downloads" > "$OUT"
fi

gh api "repos/$REPO/releases" \
  --jq '.[] | . as $r | .assets[] | [$r.tag_name, .name, .download_count] | @csv' \
  | while IFS= read -r row; do
      echo "\"$STAMP\",$row" >> "$OUT"
    done

TOTAL="$(gh api "repos/$REPO/releases" --jq '[.[].assets[].download_count] | add')"
echo "logged $STAMP -> $OUT (all-time downloads across releases: ${TOTAL:-0})"
