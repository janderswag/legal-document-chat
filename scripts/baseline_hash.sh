#!/usr/bin/env bash
# Canonical baseline-store hash — ONE method for Builder/Reviewer/Tester (D-55, audit canon).
# CWD-INDEPENDENT: cd's into the store so embedded paths are always "./…", giving the SAME
# string regardless of how/where it is invoked (fixes the cross-role divergence, carry-fwd a).
# A baseline is byte-identical iff its hash is unchanged. Usage:
#   scripts/baseline_hash.sh                       # all three baselines
#   scripts/baseline_hash.sh pipeline/.lancedb     # one store (relative or absolute)
set -euo pipefail
fold() { ( cd "$1" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256 | shasum -a 256 | awk '{print $1}' ); }
stores=( "${@:-pipeline/.lancedb pipeline/.lancedb_full pipeline/.lancedb_hyb}" )
for s in ${stores[@]}; do [ -d "$s" ] && printf '%s  %s\n' "$(fold "$s")" "$s"; done
