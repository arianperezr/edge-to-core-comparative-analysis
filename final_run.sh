#!/usr/bin/env bash
# One-command data-collection wrapper for final benchmark campaigns.
# - No plotting here (analysis is done later on a designated laptop).
# - Runs a quick smoke test first unless SKIP_SMOKE=true.

set -euo pipefail

ITERATIONS="${ITERATIONS:-100}"
SCENARIOS="${SCENARIOS:-baseline,sustained,io_concurrency}"
SMOKE_ITERATIONS="${SMOKE_ITERATIONS:-1}"
SMOKE_SCENARIOS="${SMOKE_SCENARIOS:-baseline}"
SKIP_SMOKE="${SKIP_SMOKE:-false}"

echo "======================================================="
echo "Final Data Collection Wrapper"
echo "ITERATIONS=$ITERATIONS"
echo "SCENARIOS=$SCENARIOS"
echo "SKIP_SMOKE=$SKIP_SMOKE"
echo "======================================================="

if [[ "$SKIP_SMOKE" != "true" ]]; then
  echo
  echo "[1/2] Smoke test collection"
  ITERATIONS="$SMOKE_ITERATIONS" SCENARIOS="$SMOKE_SCENARIOS" ./collect_data.sh
fi

echo
echo "[2/2] Full collection"
ITERATIONS="$ITERATIONS" SCENARIOS="$SCENARIOS" ./collect_data.sh

echo
echo "Collection complete."
echo "Results are in the newest folder under results/."
